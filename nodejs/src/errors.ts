export class Ice9Error extends Error {
  constructor(message: string) {
    super(message);
    this.name = "Ice9Error";
  }
}

export class AuthError extends Ice9Error {
  constructor(message = "API key is missing, invalid, or deactivated.") {
    super(message);
    this.name = "AuthError";
  }
}

export class RateLimitError extends Ice9Error {
  retryAfter?: number;

  constructor(message: string, retryAfter?: number) {
    super(message);
    this.name = "RateLimitError";
    this.retryAfter = retryAfter;
  }
}

export class ImageRejectedError extends Ice9Error {
  constructor(message: string) {
    super(message);
    this.name = "ImageRejectedError";
  }
}

export class AnalysisTimeoutError extends Ice9Error {
  constructor(message: string) {
    super(message);
    this.name = "AnalysisTimeoutError";
  }
}

export class PartialResultError extends Ice9Error {
  result: unknown;

  constructor(message: string, result: unknown) {
    super(message);
    this.name = "PartialResultError";
    this.result = result;
  }
}
