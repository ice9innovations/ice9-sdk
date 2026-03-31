import { describe, expect, test } from "vitest";

import { AnalysisResult, CENSOR_LABELS, ServiceResult } from "../src/index.js";
import {
  STATUS_COMPLETE,
  STATUS_COMPLETE_BASIC,
  STATUS_COMPLETE_WITH_TERMINAL_FAILURE,
} from "./fixtures.js";

describe("ServiceResult", () => {
  test("attribute-like access reads service keys", () => {
    const result = new ServiceResult({ detections: [], safe: true });
    expect(result.detections).toEqual([]);
    expect(result.safe).toBe(true);
  });

  test("predictions returns empty list when absent", () => {
    const result = new ServiceResult({ dominant: ["#fff"] });
    expect(result.predictions).toEqual([]);
  });
});

describe("AnalysisResult", () => {
  test("dynamic service access works", () => {
    const result = AnalysisResult.fromStatus(STATUS_COMPLETE);
    expect(result.nudenet).toBeInstanceOf(ServiceResult);
    expect(result.colors).toBeInstanceOf(ServiceResult);
    expect(result.nonexistent_service).toBeNull();
  });

  test("caption prefers summary and nouns reflect consensus helpers", () => {
    const result = AnalysisResult.fromStatus(STATUS_COMPLETE_BASIC);
    expect(result.caption).toBe("A dog is sitting on a hardwood floor.");
    expect(result.nouns?.validated[0]).toMatchObject({ canonical: "dog" });
    expect(result.nouns?.regions[0]).toMatchObject({ label: "dog" });
  });

  test("isNsfw returns false when moderation signals exist and no detections are flagged", () => {
    const result = AnalysisResult.fromStatus(STATUS_COMPLETE);
    expect(result.isNsfw).toBe(false);
    expect(result.isSafe).toBe(true);
  });

  test("terminal failures preserve metadata", () => {
    const result = AnalysisResult.fromStatus(STATUS_COMPLETE_WITH_TERMINAL_FAILURE);
    expect((result as any).pose.error_message).toBe("worker returned terminal failure");
    expect((result as any).pose.status).toBe("failed");
  });

  test("toJson nests services under services", () => {
    const result = AnalysisResult.fromStatus(STATUS_COMPLETE);
    const parsed = JSON.parse(result.toJson());
    expect(parsed.services.nudenet).toEqual({ detections: [] });
  });

  test("default censor label set excludes belly", () => {
    expect(CENSOR_LABELS.has("BELLY_EXPOSED")).toBe(false);
  });
});
