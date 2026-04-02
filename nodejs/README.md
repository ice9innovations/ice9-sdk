# @ice9/sdk

Node.js SDK for the [ice9](https://ice9.ai) image analysis API.

## Installation

```bash
npm install @ice9/sdk
```

## Quickstart

```ts
import { Ice9 } from "@ice9/sdk";

const client = new Ice9({ apiKey: process.env.ICE9_API_KEY });

const image = await client.analyze("photo.jpg");

if (image.isNsfw) {
  console.log(image.moderation.reason);
} else if (image.scene) {
  console.log(image.category);
  console.log(image.scene.people);
  console.log(image.scene.gender);
}
```

## Notes

- `analyze()` accepts local file paths, URLs, and in-memory image bytes.
- `image.category` exposes the canonical content-analysis category when available.
- `image.scene` adds product-shaped helpers on top of raw service payloads.
- `image.moderation.censor()` supports fill and pixelate redaction methods.

## Repository

This package is developed in the `nodejs/` subdirectory of the main SDK repo:

- https://github.com/ice9innovations/ice9-sdk
