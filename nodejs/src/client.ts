import { readFile } from "node:fs/promises";
import { basename } from "node:path";

import {
  AnalysisTimeoutError,
  AuthError,
  Ice9Error,
  ImageRejectedError,
  PartialResultError,
  RateLimitError,
} from "./errors.js";
import { AnalysisResult } from "./result.js";

const BASELINE_TIER = "basic";
const DEFAULT_BASE_URL = "https://api.ice9.ai";
const DEFAULT_TIMEOUT_MS = 95_000;
const POLL_INTERVAL_MS = 250;
const DEFAULT_MAX_RETRIES = 3;
const MAX_URL_DOWNLOAD_BYTES = 10 * 1024 * 1024;

type FetchLike = typeof fetch;

export interface Ice9Options {
  apiKey?: string;
  baseUrl?: string;
  timeout?: number;
  maxRetries?: number;
  fetch?: FetchLike;
}

export interface AnalyzeOptions {
  tier?: string;
  imageGroup?: string;
  /** MIME type for in-memory image bytes. Validated against the file signature. */
  mediaType?: "image/jpeg" | "image/png" | "image/webp" | "image/heic" | "image/heif";
  /** Multipart filename for in-memory image bytes. Its extension is normalized to the image type. */
  filename?: string;
  timeout?: number;
  stream?: boolean;
  raiseOnPartial?: boolean;
}

type SupportedImage = {
  mediaType: "image/jpeg" | "image/png" | "image/webp" | "image/heic" | "image/heif";
  extension: ".jpg" | ".png" | ".webp" | ".heic" | ".heif";
};

function detectImage(bytes: Uint8Array): SupportedImage | undefined {
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) {
    return { mediaType: "image/jpeg", extension: ".jpg" };
  }
  if (
    bytes.length >= 8 &&
    bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47 &&
    bytes[4] === 0x0d && bytes[5] === 0x0a && bytes[6] === 0x1a && bytes[7] === 0x0a
  ) {
    return { mediaType: "image/png", extension: ".png" };
  }
  if (
    bytes.length >= 12 &&
    bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46 &&
    bytes[8] === 0x57 && bytes[9] === 0x45 && bytes[10] === 0x42 && bytes[11] === 0x50
  ) {
    return { mediaType: "image/webp", extension: ".webp" };
  }
  if (
    bytes.length >= 12 &&
    bytes[4] === 0x66 && bytes[5] === 0x74 && bytes[6] === 0x79 && bytes[7] === 0x70
  ) {
    const boxLength = Math.min(
      bytes.length,
      (bytes[0] * 0x1000000) + (bytes[1] * 0x10000) + (bytes[2] * 0x100) + bytes[3],
    );
    const brands = new Set<string>();
    for (let offset = 8; offset + 3 < boxLength; offset += 4) {
      if (offset === 12) continue; // minor_version is not a brand
      brands.add(String.fromCharCode(...bytes.subarray(offset, offset + 4)));
    }
    if (["heic", "heix", "hevc", "hevx", "heim", "heis"].some((brand) => brands.has(brand))) {
      return { mediaType: "image/heic", extension: ".heic" };
    }
    if (!["avif", "avis"].some((brand) => brands.has(brand)) && ["mif1", "msf1"].some((brand) => brands.has(brand))) {
      return { mediaType: "image/heif", extension: ".heif" };
    }
  }
  return undefined;
}

function multipartImage(
  bytes: Uint8Array,
  mediaType?: AnalyzeOptions["mediaType"],
  filename?: string,
) {
  const detected = detectImage(bytes);
  if (!detected) {
    throw new ImageRejectedError(
      "Could not identify image bytes. Supported in-memory formats are JPEG, PNG, WebP, HEIC, and HEIF.",
    );
  }
  if (mediaType && mediaType !== detected.mediaType) {
    throw new ImageRejectedError(
      `The supplied mediaType ${mediaType} does not match the detected ${detected.mediaType} image.`,
    );
  }

  const requestedName = basename(filename || "upload");
  const stem = requestedName.replace(/\.[^./\\]+$/, "") || "upload";
  return {
    blob: new Blob([Buffer.from(bytes)], { type: detected.mediaType }),
    filename: `${stem}${detected.extension}`,
  };
}

function isUrl(value: string) {
  return value.startsWith("http://") || value.startsWith("https://");
}

function parseRetryAfter(response: Response) {
  const value = response.headers.get("Retry-After");
  if (!value) {
    return undefined;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

async function errorMessage(response: Response) {
  try {
    const data = (await response.clone().json()) as { error?: string; detail?: string };
    return data.error ?? data.detail ?? null;
  } catch {
    return null;
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function* sseEvents(
  stream: ReadableStream<Uint8Array>,
  onActivity?: () => void,
): AsyncGenerator<{ event: string | null; data: string | null }> {
  const decoder = new TextDecoder();
  let buffer = "";
  let event: string | null = null;
  let data: string | null = null;

  for await (const chunk of stream) {
    onActivity?.();
    buffer += decoder.decode(chunk, { stream: true });

    while (true) {
      const index = buffer.indexOf("\n");
      if (index < 0) {
        break;
      }
      const line = buffer.slice(0, index).replace(/\r$/, "");
      buffer = buffer.slice(index + 1);

      if (line === "") {
        yield { event, data };
        event = null;
        data = null;
        continue;
      }
      if (line.startsWith(":")) {
        continue;
      }
      if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        data = line.slice(5).trim();
      }
    }
  }
}

export class Ice9 {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly maxRetries: number;
  private readonly fetchImpl: FetchLike;

  constructor(options: Ice9Options = {}) {
    const apiKey = options.apiKey ?? process.env.ICE9_API_KEY;
    if (!apiKey) {
      throw new AuthError(
        "No API key provided. Pass apiKey or set the ICE9_API_KEY environment variable.",
      );
    }

    this.apiKey = apiKey;
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.timeoutMs = Math.round((options.timeout ?? DEFAULT_TIMEOUT_MS / 1000) * 1000);
    this.maxRetries = options.maxRetries ?? DEFAULT_MAX_RETRIES;
    this.fetchImpl = options.fetch ?? fetch;
  }

  async tiers() {
    const response = await this.request("/tiers", { method: "GET" });
    const body = (await response.json()) as { tiers: Record<string, string[]> };
    return body.tiers;
  }

  async services() {
    const response = await this.request("/services", { method: "GET" });
    const body = (await response.json()) as { services: string[] };
    return body.services;
  }

  async getResult(imageId: number) {
    const response = await this.request(`/results/${imageId}`, { method: "GET" });
    return AnalysisResult.fromStatus((await response.json()) as never);
  }

  async getStatus(imageId: number) {
    const response = await this.request(`/status/${imageId}`, { method: "GET" });
    return response.json();
  }

  analyze(
    image: string | URL | Buffer | Uint8Array,
    options?: AnalyzeOptions & { stream?: false | undefined },
  ): Promise<AnalysisResult>;
  analyze(
    image: string | URL | Buffer | Uint8Array,
    options: AnalyzeOptions & { stream: true },
  ): AsyncIterable<AnalysisResult>;
  analyze(
    image: string | URL | Buffer | Uint8Array,
    options: AnalyzeOptions = {},
  ): Promise<AnalysisResult> | AsyncIterable<AnalysisResult> {
    const timeoutMs = Math.round((options.timeout ?? this.timeoutMs / 1000) * 1000);

    if (options.stream) {
      const self = this;
      return {
        async *[Symbol.asyncIterator]() {
          const imageId = await self.upload(image, options);
          yield* self.stream(imageId, timeoutMs, options.raiseOnPartial ?? true);
        },
      };
    }

    return (async () => {
      const imageId = await this.upload(image, options);
      await this.poll(imageId, Date.now() + timeoutMs);
      const result = await this.getResult(imageId);
      return this.handlePartialResult(result, options.raiseOnPartial ?? true);
    })();
  }

  private async request(path: string, init: RequestInit, retryable = true) {
    let lastNetworkError: unknown;

    for (let attempt = 0; attempt <= this.maxRetries; attempt += 1) {
      try {
        const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
          ...init,
          headers: {
            "X-API-Key": this.apiKey,
            ...(init.headers ?? {}),
          },
          signal: init.signal ?? AbortSignal.timeout(this.timeoutMs),
        });

        if (response.status === 401) {
          throw new AuthError("Invalid or deactivated API key");
        }
        if (response.status === 404 && (path.startsWith("/results/") || path.startsWith("/status/"))) {
          throw new Ice9Error(`Image ${path.split("/").at(-1)} not found`, undefined, 404);
        }
        if (response.status === 429) {
          if (attempt < this.maxRetries && retryable) {
            await sleep((parseRetryAfter(response) ?? 1) * 1000);
            continue;
          }
          throw new RateLimitError(
            `Rate limit exceeded on ${path}`,
            parseRetryAfter(response),
          );
        }
        if (response.status === 400 && path === "/analyze") {
          throw new ImageRejectedError((await errorMessage(response)) ?? "Image rejected by server");
        }
        if (response.status >= 500 && response.status < 600 && attempt < this.maxRetries && retryable) {
          await sleep((2 ** attempt) * 1000);
          continue;
        }
        if (!response.ok) {
          const detail = await errorMessage(response);
          throw new Ice9Error(
            detail ? `${response.status}: ${detail}` : `Unexpected status ${response.status} from ${path}`,
            undefined,
            response.status,
          );
        }
        return response;
      } catch (error) {
        lastNetworkError = error;
        if (error instanceof Ice9Error) {
          throw error;
        }
        if (attempt < this.maxRetries && retryable) {
          await sleep((2 ** attempt) * 1000);
          continue;
        }
      }
    }

    const detail = lastNetworkError instanceof Error ? `: ${lastNetworkError.message}` : "";
    throw new Ice9Error(`Request to ${path} failed${detail}`, { cause: lastNetworkError });
  }

  private async upload(image: string | URL | Buffer | Uint8Array, options: AnalyzeOptions) {
    const tier = options.tier ?? BASELINE_TIER;
    const imageGroup = options.imageGroup ?? "api";
    if (image instanceof URL || (typeof image === "string" && isUrl(image))) {
      return this.uploadFromUrl(String(image), tier, imageGroup);
    }

    const form = new FormData();
    form.set("tier", tier);
    form.set("image_group", imageGroup);

    if (typeof image === "string") {
      const bytes = await readFile(image);
      const file = multipartImage(bytes, options.mediaType, options.filename ?? basename(image));
      form.set("file", file.blob, file.filename);
    } else {
      const file = multipartImage(Buffer.from(image), options.mediaType, options.filename);
      form.set("file", file.blob, file.filename);
    }

    const response = await this.request("/analyze", { method: "POST", body: form }, false);
    const body = (await response.json()) as { image_id: number };
    return body.image_id;
  }

  private async uploadFromUrl(url: string, tier: string, imageGroup: string) {
    let response: Response;
    try {
      response = await this.fetchImpl(url, { signal: AbortSignal.timeout(this.timeoutMs) });
    } catch (error) {
      if (error instanceof Error && error.name === "TimeoutError") {
        throw new ImageRejectedError(`Timeout downloading image from URL: ${url}`);
      }
      throw new ImageRejectedError(`Could not connect to URL: ${url}`);
    }

    if (response.status === 404) {
      throw new ImageRejectedError(`Image not found at URL: ${url}`);
    }
    if (!response.ok) {
      throw new ImageRejectedError(`Failed to download image from URL (HTTP ${response.status}): ${url}`);
    }

    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.startsWith("image/")) {
      throw new ImageRejectedError(`URL does not point to an image (content-type: ${contentType}): ${url}`);
    }

    if (!response.body) {
      throw new ImageRejectedError(`Image download did not include a response body: ${url}`);
    }

    const chunks: Buffer[] = [];
    let totalBytes = 0;
    for await (const chunk of response.body) {
      totalBytes += chunk.byteLength;
      if (totalBytes > MAX_URL_DOWNLOAD_BYTES) {
        throw new ImageRejectedError(`Image at URL exceeds 10MB limit: ${url}`);
      }
      chunks.push(Buffer.from(chunk));
    }
    const bytes = Buffer.concat(chunks);

    const filename = basename(new URL(url).pathname) || "download.jpg";
    const file = multipartImage(bytes, undefined, filename);
    const form = new FormData();
    form.set("tier", tier);
    form.set("image_group", imageGroup);
    form.set("file", file.blob, file.filename);

    const uploadResponse = await this.request("/analyze", { method: "POST", body: form }, false);
    const body = (await uploadResponse.json()) as { image_id: number };
    return body.image_id;
  }

  private async poll(imageId: number, deadlineMs: number) {
    let consecutiveErrors = 0;

    while (Date.now() < deadlineMs) {
      try {
        const response = await this.request(`/status/${imageId}`, { method: "GET" }, false);
        const body = (await response.json()) as { is_complete?: boolean };
        if (body.is_complete) {
          return body;
        }
        consecutiveErrors = 0;
        await sleep(Math.min(POLL_INTERVAL_MS, Math.max(0, deadlineMs - Date.now())));
      } catch (error) {
        if (error instanceof AuthError) {
          throw error;
        }
        if (error instanceof RateLimitError) {
          consecutiveErrors = 0;
          const waitMs = (error.retryAfter ?? POLL_INTERVAL_MS / 1000) * 1000;
          await sleep(Math.min(waitMs, Math.max(0, deadlineMs - Date.now())));
          continue;
        }
        if (error instanceof Ice9Error) {
          if (error.status != null && error.status < 500) {
            throw error;
          }
          consecutiveErrors += 1;
          if (consecutiveErrors > 2) {
            throw error;
          }
          await sleep(Math.min(2_000, Math.max(0, deadlineMs - Date.now())));
          continue;
        }
        throw error;
      }
    }

    throw new AnalysisTimeoutError(
      `Analysis of image ${imageId} did not complete within the timeout`,
    );
  }

  private handlePartialResult(result: AnalysisResult, raiseOnPartial: boolean) {
    if (Object.keys(result.servicesFailed).length > 0) {
      if (raiseOnPartial) {
        throw new PartialResultError(
          `Analysis completed with failed services: ${Object.keys(result.servicesFailed).join(", ")}`,
          result,
        );
      }
      console.warn(
        `Analysis completed with failed services: ${Object.keys(result.servicesFailed).join(", ")}`,
      );
    }
    return result;
  }

  private mergeStreamAccumulatedResults(
    result: AnalysisResult,
    accumulated: Record<string, Record<string, unknown>>,
  ) {
    if (Object.keys(accumulated).length === 0) {
      return result;
    }

    const raw = structuredClone(result._raw);
    raw.service_results = { ...(raw.service_results ?? {}) };
    raw.services_submitted = [...(raw.services_submitted ?? [])];

    for (const [service, entry] of Object.entries(accumulated)) {
      raw.service_results[service] ??= entry;
      if (!raw.services_submitted.includes(service)) {
        raw.services_submitted.push(service);
      }
    }

    return AnalysisResult.fromStatus(raw);
  }

  private async *stream(imageId: number, inactivityTimeoutMs: number, raiseOnPartial: boolean) {
    const controller = new AbortController();
    let timeoutHandle: NodeJS.Timeout | undefined;
    let timedOut = false;

    const resetTimeout = () => {
      if (timeoutHandle) {
        clearTimeout(timeoutHandle);
      }
      timeoutHandle = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, inactivityTimeoutMs);
    };

    try {
      const response = await this.request(
        `/stream/${imageId}`,
        {
          method: "GET",
          headers: { Accept: "text/event-stream" },
          signal: controller.signal,
        },
        false,
      );
      if (!response.body) {
        throw new Ice9Error("Streaming response did not include a body");
      }

      const accumulated: Record<string, Record<string, unknown>> = {};
      resetTimeout();
      for await (const message of sseEvents(response.body, resetTimeout)) {
        if (!message.event || !message.data) {
          continue;
        }
        let payload: Record<string, unknown>;
        try {
          payload = JSON.parse(message.data) as Record<string, unknown>;
        } catch {
          continue;
        }

        if (message.event === "service_complete") {
          const service = String(payload.service);
          const result = payload.result as Record<string, unknown>;
          const resultData =
            result && Object.hasOwn(result, "data")
              ? ((result.data as Record<string, unknown>) ?? {})
              : result;
          const clusterId =
            resultData && typeof resultData === "object" ? resultData.cluster_id : undefined;

          if (clusterId != null && Array.isArray(resultData.predictions)) {
            const predictions = resultData.predictions.map((prediction) => ({
              ...(prediction as Record<string, unknown>),
              cluster_id: clusterId,
            }));
            const existing = accumulated[service]?.predictions;
            accumulated[service] = {
              predictions: [...(Array.isArray(existing) ? existing : []), ...predictions],
            };
          } else {
            accumulated[service] = result;
          }

          yield AnalysisResult.fromPartial(imageId, accumulated);
          continue;
        }

        if (message.event === "complete") {
          const final = await this.getResult(imageId);
          yield this.handlePartialResult(
            this.mergeStreamAccumulatedResults(final, accumulated),
            raiseOnPartial,
          );
          return;
        }

        if (message.event === "timeout") {
          throw new AnalysisTimeoutError(
            `Analysis of image ${imageId} did not complete within the timeout`,
          );
        }
      }
    } catch (error) {
      if (timedOut) {
        throw new AnalysisTimeoutError(
          `Stream for image ${imageId} stalled — no data received for ${Math.round(
            inactivityTimeoutMs / 1000,
          )}s`,
        );
      }
      throw error;
    } finally {
      if (timeoutHandle) {
        clearTimeout(timeoutHandle);
      }
    }
  }
}
