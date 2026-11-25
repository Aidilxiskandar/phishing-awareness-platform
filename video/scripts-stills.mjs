// Look-check stills: bundle once, render many frames. usage: node scripts-stills.mjs <outDir> <f1,f2,...> [scale]
import { bundle } from "@remotion/bundler";
import { selectComposition, renderStill } from "@remotion/renderer";
import path from "node:path";
import fs from "node:fs";
const [out, list, scale = "0.5"] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts") });
const composition = await selectComposition({ serveUrl, id: "mfa-fatigue", chromiumOptions: { gl: "angle" } });
for (const f of list.split(",").map(Number)) {
  const t = Date.now();
  await renderStill({ serveUrl, composition, frame: f, scale: Number(scale), output: path.join(out, `f${String(f).padStart(4, "0")}.jpg`), imageFormat: "jpeg", jpegQuality: 88, chromiumOptions: { gl: "angle" } });
  console.log(`frame ${f} ${(Date.now() - t) / 1000}s`);
}
