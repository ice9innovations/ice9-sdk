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
      fetch: async () => jsonResponse({ tiers: { free: ["nudenet"] } }),
    });
    await expect(client.tiers()).resolves.toEqual({ free: ["nudenet"] });
  });

  test("analyze supports URL uploads", async () => {
    const calls: string[] = [];
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
