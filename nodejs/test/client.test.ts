import { describe, expect, test } from "vitest";

import { AuthError, Ice9, ImageRejectedError, RateLimitError } from "../src/index.js";
import { ANALYZE_RESPONSE, MINIMAL_PNG, STATUS_COMPLETE } from "./fixtures.js";

function jsonResponse(body: unknown, init?: ResponseInit) {
  return new Response(JSON.stringify(body), {
    headers: { "content-type": "application/json" },
    ...init,
  });
}

describe("Ice9 client", () => {
  test("requires api key", () => {
    expect(() => new Ice9({ apiKey: "" })).toThrow(AuthError);
  });

  test("tiers returns API payload", async () => {
    const client = new Ice9({
      apiKey: "ice9_test",
      fetch: async () => jsonResponse({ tiers: { basic: ["nudenet"] } }),
    });
    await expect(client.tiers()).resolves.toEqual({ basic: ["nudenet"] });
  });

  test("analyze supports URL uploads", async () => {
    const calls: string[] = [];
    let submittedTier: unknown;
    const client = new Ice9({
      apiKey: "ice9_test",
      fetch: async (input, init) => {
        const url = String(input);
        calls.push(url);
        if (url === "https://example.com/photo.jpg") {
          return new Response(MINIMAL_PNG, {
            status: 200,
            headers: { "content-type": "image/jpeg" },
          });
        }
        if (url.endsWith("/analyze")) {
          submittedTier = (init?.body as FormData).get("tier");
          return jsonResponse(ANALYZE_RESPONSE, { status: 202 });
        }
        if (url.endsWith("/status/42") || url.endsWith("/results/42")) {
          return jsonResponse(STATUS_COMPLETE, { status: 200 });
        }
        return new Response(null, { status: 404 });
      },
    });

    const result = await client.analyze("https://example.com/photo.jpg");
    expect(result.imageId).toBe(42);
    expect(calls).toContain("https://example.com/photo.jpg");
    expect(submittedTier).toBe("basic");
  });

  test.each([
    {
      format: "JPEG",
      bytes: Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00]),
      type: "image/jpeg",
      filename: "photo.jpg",
    },
    {
      format: "PNG",
      bytes: MINIMAL_PNG,
      type: "image/png",
      filename: "photo.png",
    },
    {
      format: "WebP",
      bytes: Buffer.from("RIFF\x04\x00\x00\x00WEBP", "binary"),
      type: "image/webp",
      filename: "photo.webp",
    },
    {
      format: "HEIC",
      bytes: Buffer.from("000000186674797068656963000000006d696631", "hex"),
      type: "image/heic",
      filename: "photo.heic",
    },
    {
      format: "HEIF",
      bytes: Buffer.from("00000018667479706d696631000000006d736631", "hex"),
      type: "image/heif",
      filename: "photo.heif",
    },
  ])("uploads $format buffers with an accurate multipart type and filename", async ({ bytes, type, filename }) => {
    let uploadedFile: File | null = null;
    const client = new Ice9({
      apiKey: "ice9_test",
      fetch: async (input, init) => {
        const url = String(input);
        if (url.endsWith("/analyze")) {
          uploadedFile = (init?.body as FormData).get("file") as File;
          return jsonResponse(ANALYZE_RESPONSE, { status: 202 });
        }
        return jsonResponse(STATUS_COMPLETE, { status: 200 });
      },
    });

    await client.analyze(bytes, { filename: "photo.bin" });
    expect(uploadedFile).toMatchObject({ type, name: filename });
  });

  test("validates an explicit media type against in-memory image bytes", async () => {
    const client = new Ice9({ apiKey: "ice9_test" });
    await expect(
      client.analyze(MINIMAL_PNG, { mediaType: "image/jpeg" }),
    ).rejects.toThrow("does not match the detected image/png image");
  });

  test("rejects unidentifiable in-memory image bytes", async () => {
    const client = new Ice9({ apiKey: "ice9_test" });
    await expect(client.analyze(Buffer.from("not an image"))).rejects.toThrow(
      "Could not identify image bytes",
    );
  });

  test("raises rate limit errors with retry-after", async () => {
    const client = new Ice9({
      apiKey: "ice9_test",
      maxRetries: 0,
      fetch: async () =>
        jsonResponse({ error: "rate limit exceeded" }, {
          status: 429,
          headers: { "Retry-After": "5" },
        }),
    });

    await expect(client.services()).rejects.toMatchObject({
      retryAfter: 5,
    });
  });

  test("rejects non-image URLs", async () => {
    const client = new Ice9({
      apiKey: "ice9_test",
      fetch: async () =>
        new Response("not an image", {
          status: 200,
          headers: { "content-type": "text/plain" },
        }),
    });

    await expect(client.analyze("https://example.com/file.txt")).rejects.toThrow(
      ImageRejectedError,
    );
  });
});
