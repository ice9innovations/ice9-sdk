import { censor, type CensorOptions } from "./censor.js";

export interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Prediction {
  label?: string;
  confidence?: number;
  text?: string;
  bbox?: BBox;
  [key: string]: unknown;
}

export interface RawStatus {
  image_id: number;
  image_filename?: string | null;
  image_created?: string | null;
  services_submitted?: string[];
  services_failed?: Record<string, string | null>;
  service_results?: Record<string, Record<string, unknown>>;
  postprocessing?: Array<Record<string, unknown>>;
  rembg?: Record<string, unknown> | null;
  [key: string]: unknown;
}

const SERVICE_STRIP_FIELDS = new Set(["service", "status"]);

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function unwrapServiceEntry(entry: unknown): Record<string, unknown> {
  if (!isObject(entry)) {
    return {};
  }

  if (!Object.hasOwn(entry, "data")) {
    return entry;
  }

  const data = entry.data;
  const metadata = Object.fromEntries(
    Object.entries(entry).filter(([key]) => key !== "data" && key !== "processing_time"),
  );

  if (isObject(data)) {
    return { ...metadata, ...data };
  }
  if (data == null) {
    return metadata;
  }
  return { ...metadata, value: data };
}

export class ServiceResult {
  [key: string]: unknown;
  readonly _data: Record<string, unknown>;
  readonly processingTime?: number;

  constructor(data: Record<string, unknown> = {}, processingTime?: number) {
    this._data = data;
    this.processingTime = processingTime;

    return new Proxy(this, {
      get: (target, prop, receiver) => {
        if (typeof prop !== "string") {
          return Reflect.get(target, prop, receiver);
        }
        if (prop in target) {
          return Reflect.get(target, prop, receiver);
        }
        if (prop in target._data) {
          return target._data[prop];
        }
        throw new Error(
          `ServiceResult has no attribute ${JSON.stringify(prop)}. Available keys: ${Object.keys(target._data).join(", ")}`,
        );
      },
    });
  }

  get predictions(): Prediction[] {
    const predictions = this._data.predictions;
    return Array.isArray(predictions) ? (predictions as Prediction[]) : [];
  }

  get text(): string | null {
    const first = this.predictions[0];
    return typeof first?.text === "string" ? first.text : null;
  }

  flaggedPredictions(options: { labels?: Set<string> | string[]; minConfidence?: number } = {}) {
    const labels =
      options.labels instanceof Set ? options.labels : new Set(options.labels ?? []);
    const minConfidence = options.minConfidence ?? 0.5;
    return this.predictions.filter(
      (prediction) =>
        Boolean(prediction.label) &&
        (labels.size === 0 || labels.has(prediction.label!)) &&
        (prediction.confidence ?? 0) >= minConfidence,
    );
  }
}

class ServicesResult {
  constructor(private readonly serviceResults: Record<string, ServiceResult>) {
    return new Proxy(this, {
      get: (target, prop, receiver) => {
        if (typeof prop !== "string") {
          return Reflect.get(target, prop, receiver);
        }
        if (prop in target) {
          return Reflect.get(target, prop, receiver);
        }
        return target.serviceResults[prop] ?? null;
      },
    });
  }

  names() {
    return Object.keys(this.serviceResults).sort();
  }
}

class ModerationResult {
  constructor(private readonly result: AnalysisResult) {}

  get reason(): string {
    const detections = this.result.nsfwDetections();
    if (detections.length > 0) {
      const labels = [...new Set(detections.map((d: Prediction) => d.label ?? "unknown"))].sort();
      return `Flagged NudeNet detections: ${labels.join(", ")}.`;
    }

    if (this.result.content_analysis && this.result.scene) {
      const parts: string[] = [];
      if (this.result.scene.type) {
        parts.push(`scene=${this.result.scene.type}`);
      }
      if (this.result.scene.intimacy) {
        parts.push(`intimacy=${this.result.scene.intimacy}`);
      }
      if (this.result.scene.activities.length > 0) {
        parts.push(`activities=${this.result.scene.activities.join(",")}`);
      }
      if (parts.length > 0) {
        return `Content analysis: ${parts.join(", ")}.`;
      }
    }

    if (this.result.nudenet) {
      return "No flagged NudeNet detections above the default threshold.";
    }

    return "No moderation signal is available on this result.";
  }

  async censor(image: string | Buffer | Uint8Array, options?: CensorOptions) {
    return censor(this.result, image, options);
  }
}

class SceneResult {
  readonly type: string | null;
  readonly intimacy: string | null;
  readonly activities: string[];
  readonly anatomyExposed: string[];
  readonly raw: Record<string, unknown>;

  constructor(data: {
    type?: string | null;
    intimacy?: string | null;
    activities?: string[];
    anatomyExposed?: string[];
    raw?: Record<string, unknown>;
  }) {
    this.type = data.type ?? null;
    this.intimacy = data.intimacy ?? null;
    this.activities = [...(data.activities ?? [])].sort();
    this.anatomyExposed = data.anatomyExposed ?? [];
    this.raw = data.raw ?? {};
  }

  get activity(): string | null {
    return this.activities.length === 1 ? this.activities[0] : null;
  }

  toJSON() {
    return {
      type: this.type,
      intimacy: this.intimacy,
      activity: this.activity,
      activities: this.activities,
      anatomy_exposed: this.anatomyExposed,
    };
  }
}

class NounsResult {
  constructor(private readonly result: AnalysisResult) {}

  get consensus() {
    return (this.result.noun_consensus?._data.nouns_all ??
      this.result.noun_consensus?._data.nouns ??
      []) as Array<Record<string, unknown>>;
  }

  get validated() {
    return (this.result.noun_consensus?._data.nouns ?? []) as Array<Record<string, unknown>>;
  }

  get regions() {
    return this.result.florence2_grounding?.predictions ?? [];
  }
}

class VerbsResult {
  constructor(private readonly result: AnalysisResult) {}

  get consensus() {
    return (this.result.verb_consensus?._data.verbs ?? []) as Array<Record<string, unknown>>;
  }
}

export class AnalysisResult {
  [key: string]: unknown;
  readonly imageId: number;
  readonly imageFilename: string | null;
  readonly imageCreated: string | null;
  readonly servicesSubmitted: string[];
  readonly servicesFailed: Record<string, string | null>;
  readonly isComplete: boolean;
  readonly _raw: RawStatus;
  private readonly _serviceResults: Record<string, ServiceResult>;

  constructor(args: {
    imageId: number;
    imageFilename?: string | null;
    imageCreated?: string | null;
    servicesSubmitted?: string[];
    servicesFailed?: Record<string, string | null>;
    serviceResults?: Record<string, ServiceResult>;
    raw?: RawStatus;
    isComplete?: boolean;
  }) {
    this.imageId = args.imageId;
    this.imageFilename = args.imageFilename ?? null;
    this.imageCreated = args.imageCreated ?? null;
    this.servicesSubmitted = args.servicesSubmitted ?? [];
    this.servicesFailed = args.servicesFailed ?? {};
    this._serviceResults = args.serviceResults ?? {};
    this._raw = args.raw ?? ({ image_id: args.imageId } as RawStatus);
    this.isComplete = args.isComplete ?? true;

    return new Proxy(this, {
      get: (target, prop, receiver) => {
        if (typeof prop !== "string") {
          return Reflect.get(target, prop, receiver);
        }
        if (prop in target) {
          return Reflect.get(target, prop, receiver);
        }
        if (prop.startsWith("_")) {
          return Reflect.get(target, prop, receiver);
        }
        return target._serviceResults[prop] ?? null;
      },
    });
  }

  get services() {
    return new ServicesResult(this._serviceResults);
  }

  private service(name: string): ServiceResult | null {
    return this._serviceResults[name] ?? null;
  }

  get nudenet(): ServiceResult | null {
    return this.service("nudenet");
  }

  get content_analysis(): ServiceResult | null {
    return this.service("content_analysis");
  }

  get noun_consensus(): ServiceResult | null {
    return this.service("noun_consensus");
  }

  get florence2_grounding(): ServiceResult | null {
    return this.service("florence2_grounding");
  }

  get verb_consensus(): ServiceResult | null {
    return this.service("verb_consensus");
  }

  get caption_summary(): ServiceResult | null {
    return this.service("caption_summary");
  }

  get caption(): string | null {
    const summary = this.caption_summary?._data.summary_caption;
    if (typeof summary === "string" && summary) {
      return summary;
    }
    for (const name of this.servicesSubmitted) {
      const service = this._serviceResults[name];
      if (service?.text) {
        return service.text;
      }
    }
    return null;
  }

  get isNsfw(): boolean | null {
    if (this.hasNsfw()) {
      return true;
    }
    if (this.nudenet || this.content_analysis) {
      return false;
    }
    return null;
  }

  get isSafe(): boolean | null {
    const value = this.isNsfw;
    return value == null ? null : !value;
  }

  get scene(): SceneResult | null {
    const fullAnalysis = this.content_analysis?._data.full_analysis;
    if (!isObject(fullAnalysis)) {
      return null;
    }
    const activityAnalysis = isObject(fullAnalysis.activity_analysis)
      ? fullAnalysis.activity_analysis
      : {};
    return new SceneResult({
      type: typeof activityAnalysis.scene_type === "string" ? activityAnalysis.scene_type : null,
      intimacy:
        typeof activityAnalysis.intimacy_level === "string"
          ? activityAnalysis.intimacy_level
          : null,
      activities: Array.isArray(activityAnalysis.activities)
        ? (activityAnalysis.activities as string[])
        : [],
      anatomyExposed: Array.isArray(fullAnalysis.anatomy_exposed)
        ? (fullAnalysis.anatomy_exposed as string[])
        : [],
      raw: fullAnalysis,
    });
  }

  get nouns() {
    const nouns = new NounsResult(this);
    return nouns.consensus.length > 0 || nouns.regions.length > 0 ? nouns : null;
  }

  get verbs() {
    const verbs = new VerbsResult(this);
    return verbs.consensus.length > 0 ? verbs : null;
  }

  get moderation() {
    return new ModerationResult(this);
  }

  nsfwDetections(options: { labels?: Set<string> | string[]; minConfidence?: number } = {}) {
    if (!this.nudenet) {
      return [];
    }
    const labels =
      options.labels instanceof Set ? options.labels : new Set(options.labels ?? []);
    return this.nudenet.flaggedPredictions({
      labels,
      minConfidence: options.minConfidence ?? 0.5,
    });
  }

  hasNsfw(options: { labels?: Set<string> | string[]; minConfidence?: number } = {}) {
    return this.nsfwDetections(options).length > 0;
  }

  toJSON() {
    const services = Object.fromEntries(
      Object.entries(this._serviceResults).map(([name, result]) => [
        name,
        Object.fromEntries(
          Object.entries(result._data).filter(([key]) => !SERVICE_STRIP_FIELDS.has(key)),
        ),
      ]),
    );

    const out: Record<string, unknown> = {
      image_id: this.imageId,
      services_submitted: this.servicesSubmitted,
      services_failed: this.servicesFailed,
      services,
    };
    if (this.imageFilename) {
      out.image_filename = this.imageFilename;
    }
    if (this.imageCreated) {
      out.image_created = this.imageCreated;
    }
    return out;
  }

  toJson(space?: number) {
    return JSON.stringify(this.toJSON(), null, space);
  }

  static fromPartial(imageId: number, accumulated: Record<string, Record<string, unknown>>) {
    const serviceResults = Object.fromEntries(
      Object.entries(accumulated).map(([name, entry]) => [
        name,
        new ServiceResult(unwrapServiceEntry(entry), Number(entry.processing_time ?? 0) || undefined),
      ]),
    );

    return new AnalysisResult({
      imageId,
      servicesSubmitted: Object.keys(accumulated),
      servicesFailed: {},
      serviceResults,
      raw: { image_id: imageId },
      isComplete: false,
    });
  }

  static fromStatus(data: RawStatus) {
    const serviceResults: Record<string, ServiceResult> = {};
    const rawServiceResults = data.service_results ?? {};
    const servicesFailed = data.services_failed ?? {};

    if (Object.keys(servicesFailed).length > 0) {
      console.warn(
        `Analysis completed with failed services: ${Object.keys(servicesFailed).join(", ")}. Results for those services will be null.`,
      );
    }

    for (const [name, entry] of Object.entries(rawServiceResults)) {
      serviceResults[name] = new ServiceResult(
        unwrapServiceEntry(entry),
        typeof entry.processing_time === "number" ? entry.processing_time : undefined,
      );
    }

    if (!serviceResults.rembg && data.rembg && isObject(data.rembg)) {
      serviceResults.rembg = new ServiceResult(
        unwrapServiceEntry(data.rembg),
        typeof data.rembg.processing_time === "number" ? data.rembg.processing_time : undefined,
      );
    }

    for (const entry of data.postprocessing ?? []) {
      if (!isObject(entry) || typeof entry.service !== "string") {
        continue;
      }
      if (serviceResults[entry.service]) {
        continue;
      }
      const current = serviceResults[entry.service];
      const unwrapped = unwrapServiceEntry(entry);
      const clusterId = unwrapped.cluster_id;
      const predictions = Array.isArray(unwrapped.predictions)
        ? unwrapped.predictions.map((prediction) =>
            isObject(prediction) && clusterId != null ? { ...prediction, cluster_id: clusterId } : prediction,
          )
        : [];

      if (current) {
        current._data.predictions = [...current.predictions, ...predictions];
      } else {
        serviceResults[entry.service] = new ServiceResult(
          predictions.length > 0 ? { predictions } : unwrapped,
          typeof entry.processing_time === "number" ? entry.processing_time : undefined,
        );
      }
    }

    return new AnalysisResult({
      imageId: data.image_id,
      imageFilename: data.image_filename ?? null,
      imageCreated: data.image_created ?? null,
      servicesSubmitted: data.services_submitted ?? [],
      servicesFailed,
      serviceResults,
      raw: data,
      isComplete: true,
    });
  }
}
