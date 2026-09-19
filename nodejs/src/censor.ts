import { readFile, writeFile } from "node:fs/promises";
import { extname } from "node:path";

import { Ice9Error } from "./errors.js";
import type { AnalysisResult, BBox, Prediction } from "./result.js";

export const CENSOR_LABELS = new Set([
  "FEMALE_BREAST_EXPOSED",
  "MALE_BREAST_EXPOSED",
  "FEMALE_GENITALIA_EXPOSED",
  "MALE_GENITALIA_EXPOSED",
  "BUTTOCKS_EXPOSED",
  "ANUS_EXPOSED",
]);

export type CensorMethod = "fill" | "pixelate";

export interface CensorOptions {
  method?: CensorMethod;
  labels?: Set<string> | string[];
  minConfidence?: number;
  output?: string;
  format?: "jpeg" | "png" | "webp";
}

async function loadSharp() {
  try {
    return (await import("sharp")).default;
  } catch (cause) {
    throw new Ice9Error(
      "Image censoring requires the optional 'sharp' package. Install it with: npm install sharp",
      { cause },
    );
  }
}

function outputFormat(
  requested: CensorOptions["format"],
  output: string | undefined,
  inputFormat: string | undefined,
): "jpeg" | "png" | "webp" {
  if (requested) return requested;
  const extension = output ? extname(output).toLowerCase() : "";
  if (extension === ".jpg" || extension === ".jpeg") return "jpeg";
  if (extension === ".png") return "png";
  if (extension === ".webp") return "webp";
  if (output && extension) {
    throw new TypeError(
      `Cannot infer a supported censor output format from ${JSON.stringify(extension)}. ` +
      "Use a .jpg, .png, or .webp filename, or set options.format.",
    );
  }
  return inputFormat === "png" || inputFormat === "webp" ? inputFormat : "jpeg";
}

function clampBox(bbox: BBox, width: number, height: number) {
  const x1 = Math.max(0, Math.trunc(bbox.x));
  const y1 = Math.max(0, Math.trunc(bbox.y));
  const x2 = Math.min(width, Math.trunc(bbox.x + bbox.width));
  const y2 = Math.min(height, Math.trunc(bbox.y + bbox.height));
  return { x1, y1, x2, y2, width: x2 - x1, height: y2 - y1 };
}

function shouldCensor(
  prediction: Prediction,
  labels: Set<string>,
  minConfidence: number,
): prediction is Prediction & { bbox: BBox } {
  return Boolean(
    prediction.label &&
      prediction.bbox &&
      labels.has(prediction.label) &&
      (prediction.confidence ?? 0) >= minConfidence,
  );
}

export async function censor(
  result: AnalysisResult,
  image: string | Buffer | Uint8Array,
  options: CensorOptions = {},
): Promise<Buffer> {
  const sharp = await loadSharp();
  if (!result.nudenet) {
    throw new Ice9Error(
      "nudenet results are not present — was nudenet included in the tier?",
    );
  }

  const method = options.method ?? "fill";
  if (method !== "fill" && method !== "pixelate") {
    throw new TypeError(
      `Unknown censor method ${JSON.stringify(method)}. Choose 'fill' or 'pixelate'.`,
    );
  }

  const labels =
    options.labels instanceof Set
      ? options.labels
      : new Set(options.labels ?? Array.from(CENSOR_LABELS));
  const minConfidence = options.minConfidence ?? 0.5;
  const input =
    typeof image === "string" ? await readFile(image) : Buffer.from(image);

  const base = sharp(input).ensureAlpha();
  const meta = await base.metadata();
  const width = meta.width ?? 0;
  const height = meta.height ?? 0;
  let current = base;

  for (const prediction of result.nudenet.predictions) {
    if (!shouldCensor(prediction, labels, minConfidence)) {
      continue;
    }

    const box = clampBox(prediction.bbox, width, height);
    if (box.width <= 0 || box.height <= 0) {
      continue;
    }

    if (method === "fill") {
      const overlay = await sharp({
        create: {
          width: box.width,
          height: box.height,
          channels: 4,
          background: { r: 0, g: 0, b: 0, alpha: 1 },
        },
      })
        .png()
        .toBuffer();

      current = current.composite([{ input: overlay, left: box.x1, top: box.y1 }]);
      continue;
    }

    const region = await current
      .clone()
      .extract({ left: box.x1, top: box.y1, width: box.width, height: box.height })
      .toBuffer();
    const block = Math.max(8, Math.floor(Math.min(box.width, box.height) / 8));
    const pixelated = await sharp(region)
      .resize(Math.max(1, Math.floor(box.width / block)), Math.max(1, Math.floor(box.height / block)), {
        kernel: "nearest",
      })
      .resize(box.width, box.height, { kernel: "nearest" })
      .png()
      .toBuffer();

    current = current.composite([{ input: pixelated, left: box.x1, top: box.y1 }]);
  }

  const format = outputFormat(options.format, options.output, meta.format);
  const output = await (format === "png"
    ? current.png()
    : format === "webp"
      ? current.webp()
      : current.jpeg()
  ).toBuffer();
  if (options.output) {
    await writeFile(options.output, output);
  }
  return output;
}
