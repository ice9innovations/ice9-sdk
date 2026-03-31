import { Ice9 } from "../src/index.js";

const client = new Ice9({ apiKey: process.env.ICE9_API_KEY });

const image = await client.analyze("photo.jpg", { tier: "basic" });

console.log(image.caption);
console.log(image.isNsfw);
console.log(image.scene?.type, image.scene?.intimacy);

for (const noun of image.nouns?.validated ?? []) {
  console.log(noun);
}
