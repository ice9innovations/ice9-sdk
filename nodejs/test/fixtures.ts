export const ANALYZE_RESPONSE = {
  image_id: 42,
  trace_id: "test-trace-001",
  tier: "basic",
  services_submitted: ["nudenet", "colors", "metadata", "ocr", "qr"],
  image_width: 1,
  image_height: 1,
};

export const STATUS_COMPLETE = {
  image_id: 42,
  image_filename: "test.png",
  image_group: "api",
  image_created: "2026-03-08T12:00:00",
  services_submitted: ["nudenet", "colors", "metadata", "ocr", "qr"],
  services_failed: {},
  is_complete: true,
  service_results: {
    nudenet: { data: { detections: [] }, processing_time: 0.4 },
    colors: { data: { dominant: ["#ffffff"] }, processing_time: 0.1 },
    metadata: { data: { width: 1, height: 1 }, processing_time: 0.1 },
    ocr: { data: { text: "" }, processing_time: 0.2 },
    qr: { data: { codes: [] }, processing_time: 0.1 },
    content_analysis: {
      full_analysis: {
        category: "safe",
        scene: {
          people: 0,
          gender: {
            presentation: "unknown",
            mixed: false,
            confidence: 0,
          },
        },
        activity_analysis: {
          scene_type: "safe",
          intimacy_level: "none",
          people_count: 0,
          activities: [],
        },
        anatomy_exposed: [],
      },
      analysis_version: "1.0",
    },
  },
  postprocessing: [],
  rembg: {
    model: "birefnet-general",
    png_b64: "aGVsbG8=",
    premasked: false,
    processing_time: 1.2,
    shape: [512, 512],
  },
};

export const STATUS_COMPLETE_BASIC = {
  ...STATUS_COMPLETE,
  services_submitted: [
    "nudenet",
    "colors",
    "moondream",
    "qwen",
    "florence2_grounding",
    "noun_consensus",
    "caption_summary",
  ],
  service_results: {
    ...STATUS_COMPLETE.service_results,
    moondream: {
      data: { predictions: [{ text: "a dog sitting on a wooden floor" }] },
      processing_time: 1.2,
    },
    qwen: {
      data: { predictions: [{ text: "a brown dog on a hardwood floor" }] },
      processing_time: 2.1,
    },
    florence2_grounding: {
      data: {
        predictions: [
          { label: "dog", bbox: { x: 50, y: 80, width: 200, height: 180 } },
        ],
      },
      processing_time: 0.9,
    },
    noun_consensus: {
      nouns: [
        {
          canonical: "dog",
          category: "animal",
          confidence: 1,
          grounding_validated: true,
          vote_count: 2,
        },
      ],
      nouns_all: [
        {
          canonical: "dog",
          category: "animal",
          confidence: 1,
          grounding_validated: true,
          vote_count: 2,
        },
        {
          canonical: "floor",
          category: "object",
          confidence: 0.4,
          grounding_validated: false,
          vote_count: 1,
        },
      ],
    },
    caption_summary: {
      summary_caption: "A dog is sitting on a hardwood floor.",
    },
  },
};

export const STATUS_COMPLETE_WITH_TERMINAL_FAILURE = {
  ...STATUS_COMPLETE,
  services_failed: { pose: "worker returned terminal failure" },
  services_submitted: [...STATUS_COMPLETE.services_submitted, "pose"],
  service_results: {
    ...STATUS_COMPLETE.service_results,
    pose: {
      status: "failed",
      error_message: "worker returned terminal failure",
      data: null,
      processing_time: 0.3,
    },
  },
};

export const MINIMAL_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);
