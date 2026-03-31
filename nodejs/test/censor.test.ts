import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import sharp from "sharp";
import { describe, expect, test } from "vitest";

import { AnalysisResult } from "../src/index.js";
import { STATUS_COMPLETE } from "./fixtures.js";

const NUDENET_PREDICTIONS = [
  {
    label: "FEMALE_BREAST_EXPOSED",
    confidence: 0.85,
    bbox: { x: 100, y: 100, width: 80, height: 90 },
  },
  {
    label: "BELLY_EXPOSED",
    confidence: 0.9,
    bbox: { x: 120, y: 200, width: 100, height: 80 },
  },
];

async function gradientImage(width: number, height: number) {
  const channels = 3;
  const data = Buffer.alloc(width * height * channels);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = (y * width + x) * channels;
      data[index] = 50 + Math.floor((150 * x) / width);
      data[index + 1] = 80 + Math.floor((70 * y) / height);
      data[index + 2] = 120;
    }
  }
  return sharp(data, { raw: { width, height, channels } }).jpeg().toBuffer();
}

async function pixel(buffer: Buffer, x: number, y: number) {
  const { data, info } = await sharp(buffer).raw().toBuffer({ resolveWithObject: true });
  const index = (y * info.width + x) * info.channels;
  return Array.from(data.slice(index, index + 3));
}

describe("censor", () => {
  test("fill blacks out selected regions", async () => {
    const status = structuredClone(STATUS_COMPLETE);
    status.service_results.nudenet = { data: { predictions: NUDENET_PREDICTIONS } } as never;
    const result = AnalysisResult.fromStatus(status);
    const image = await gradientImage(500, 600);

    const censored = await result.moderation.censor(image, { method: "fill" });
    expect(await pixel(censored, 140, 145)).toEqual([0, 0, 0]);
    expect(await pixel(censored, 170, 240)).not.toEqual([0, 0, 0]);
  });

  test("pixelate changes the source region", async () => {
    const status = structuredClone(STATUS_COMPLETE);
    status.service_results.nudenet = { data: { predictions: NUDENET_PREDICTIONS } } as never;
    const result = AnalysisResult.fromStatus(status);
    const image = await gradientImage(500, 600);

    const censored = await result.moderation.censor(image, { method: "pixelate" });
    expect(await pixel(censored, 140, 145)).not.toEqual(await pixel(image, 140, 145));
  });

  test("writes to output path when requested", async () => {
    const status = structuredClone(STATUS_COMPLETE);
    status.service_results.nudenet = { data: { predictions: NUDENET_PREDICTIONS } } as never;
    const result = AnalysisResult.fromStatus(status);
    const image = await gradientImage(500, 600);
    const dir = await mkdtemp(join(tmpdir(), "ice9-nodejs-"));
    const input = join(dir, "input.jpg");
    const output = join(dir, "output.jpg");

    await writeFile(input, image);
    await result.moderation.censor(input, { output });

    const written = await readFile(output);
    expect(written.byteLength).toBeGreaterThan(0);
  });
});
