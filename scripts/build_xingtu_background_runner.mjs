import fs from "node:fs/promises";

const [runnerPath, outputPath, downloadName] = process.argv.slice(2);
if (!runnerPath || !outputPath || !downloadName) {
  throw new Error("usage: build_xingtu_background_runner.mjs RUNNER OUTPUT DOWNLOAD_NAME");
}
let source = await fs.readFile(runnerPath, "utf8");
const replacements = [
  ['"delivery_mode": "return"', '"delivery_mode": "download"'],
  ['downloadJson("xingtu-capture.json", state);', `downloadJson(${JSON.stringify(downloadName)}, state);`],
];
for (const [before, after] of replacements) {
  if (!source.includes(before)) throw new Error(`runner structure changed: missing ${before}`);
  source = source.replace(before, after);
}
await fs.writeFile(outputPath, source);
console.log(JSON.stringify({ok: true, output: outputPath, download: downloadName}));
