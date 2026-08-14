import fs from "node:fs/promises";
import path from "node:path";

const LABELS = [
  { label: "达人概览", field: "overview", column: "达人概览" },
  { label: "商业能力", field: "commercial", column: "商业能力" },
  { label: "创作能力", field: "creative", column: "创作能力" },
  { label: "履约能力", field: "contract", column: "履约能力" },
  { label: "连接用户", field: "connect", column: "连接用户" },
];

export function columnLetter(index) {
  let value = index + 1;
  let output = "";
  while (value > 0) {
    value -= 1;
    output = String.fromCharCode(65 + (value % 26)) + output;
    value = Math.floor(value / 26);
  }
  return output;
}

export function regionFromLines(lines) {
  const cleaned = lines.map((line) => String(line || "").trim()).filter(Boolean);
  const index = cleaned.indexOf("地区");
  if (index < 0) return "";
  const candidate = cleaned[index + 1] || "";
  return ["介绍", "性别", "行业标签", "内容主题", "达人类型"].includes(candidate) ? "" : candidate;
}

async function pageRegion(tab) {
  return tab.playwright.evaluate(() => {
    const infoItems = [...document.querySelectorAll(".info-item")];
    for (const item of infoItems) {
      const label = item.querySelector(".label");
      if ((label?.textContent || "").trim() !== "地区") continue;
      return (item.querySelector(".value")?.textContent || "").trim();
    }
    const leaves = [...document.querySelectorAll("*")].filter(
      (element) => element.childElementCount === 0 && (element.textContent || "").trim() === "地区",
    );
    for (const leaf of leaves) {
      let scope = leaf.parentElement;
      for (let depth = 0; depth < 4 && scope; depth += 1, scope = scope.parentElement) {
        const lines = (scope.innerText || "").split(/\n+/).map((line) => line.trim()).filter(Boolean);
        const index = lines.indexOf("地区");
        if (index >= 0 && lines[index + 1]) return lines[index + 1];
      }
    }
    return "";
  }, undefined, { timeoutMs: 15000 });
}

export async function collectRegions({ chrome, tab, records, outFile, onProgress = async () => {} }) {
  if (!chrome || !tab) throw new Error("chrome 和 tab 必填");
  const results = [];
  await chrome.nameSession("📍 达人地区批处理");
  for (let index = 0; index < records.length; index += 1) {
    const creator = records[index];
    const url = `https://www.xingtu.cn/ad/creator/author-homepage/douyin-video/${creator.star_id}?possessStarId`;
    await tab.goto(url);
    await tab.playwright.waitForLoadState({ state: "domcontentloaded", timeoutMs: 30000 });
    try {
      await tab.playwright.getByText("地区", { exact: true }).waitFor({ state: "visible", timeoutMs: 5000 });
    } catch (_) {
      await tab.playwright.waitForTimeout(1200);
    }
    const region = String(await pageRegion(tab) || "").trim();
    const result = {
      index,
      lark_row: Number(creator.lark_row ?? index + 2),
      name: creator.platform_name || creator.source_name || "",
      star_id: String(creator.star_id || ""),
      region,
    };
    results.push(result);
    if (outFile) await fs.writeFile(path.resolve(outFile), JSON.stringify(results, null, 2));
    await onProgress({ completed: index + 1, total: records.length, result });
  }
  return results;
}

async function contentBox(tab) {
  return tab.playwright.evaluate(() => {
    const element = document.querySelector(".tabs-content");
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
  }, undefined, { timeoutMs: 15000 });
}

export async function captureAbilityScreenshots({
  chrome,
  tab,
  records,
  columns,
  outDir,
  startIndex = 0,
  waitMs = 1300,
  maxViewportHeight = 6000,
  resume = true,
  onProgress = async () => {},
}) {
  if (!chrome || !tab) throw new Error("chrome 和 tab 必填");
  if (!Array.isArray(records) || !records.length) throw new Error("records 必须是非空数组");
  if (!Array.isArray(columns) || columns[0] !== "地区") throw new Error("最新版列必须以‘地区’开头");
  const missingColumns = LABELS.map((item) => item.column).filter((column) => !columns.includes(column));
  if (missingColumns.length) throw new Error(`缺少截图列: ${missingColumns.join("、")}`);

  const root = path.resolve(outDir);
  await fs.mkdir(root, { recursive: true });
  const checkpointPath = path.join(root, "ability-checkpoint.json");
  const manifestPath = path.join(root, "ability-image-manifest.json");
  const viewport = await chrome.capabilities.get("viewport");
  let results = [];
  let manifest = [];
  let effectiveStart = startIndex;
  if (resume) {
    try { results = JSON.parse(await fs.readFile(checkpointPath, "utf8")); } catch (_) { results = []; }
    try { manifest = JSON.parse(await fs.readFile(manifestPath, "utf8")); } catch (_) { manifest = []; }
    const firstFailed = results.findIndex((item) => (item.errors || []).length > 0);
    effectiveStart = Math.max(startIndex, firstFailed >= 0 ? firstFailed : results.length);
    results = results.slice(0, effectiveStart);
    const resumeRow = Number(records[effectiveStart]?.lark_row ?? effectiveStart + 2);
    manifest = manifest.filter((item) => Number(item.row) < resumeRow);
  }

  await chrome.nameSession("📊 达人能力截图批处理");
  try {
    for (let index = effectiveStart; index < records.length; index += 1) {
      const creator = records[index];
      const larkRow = Number(creator.lark_row ?? index + 2);
      const url = `https://www.xingtu.cn/ad/creator/author-homepage/douyin-video/${creator.star_id}?possessStarId`;
      const result = {
        index,
        lark_row: larkRow,
        name: creator.platform_name || creator.source_name || "",
        star_id: String(creator.star_id || ""),
        region: "",
        images: {},
        missing: [],
        errors: [],
      };
      await viewport.set({ width: 1920, height: 2200 });
      await tab.goto(url);
      await tab.playwright.waitForLoadState({ state: "domcontentloaded", timeoutMs: 30000 });
      await tab.playwright.waitForTimeout(1800);
      result.region = String(await pageRegion(tab) || "").trim();

      for (const item of LABELS) {
        try {
          const locator = tab.playwright.getByRole("tab", { name: item.label, exact: true });
          if (!(await locator.count()) || !(await locator.first().isVisible())) {
            result.missing.push(item.field);
            continue;
          }
          await locator.first().click({ timeoutMs: 10000 });
          await tab.playwright.waitForTimeout(waitMs);
          let box = await contentBox(tab);
          if (!box) throw new Error("未找到 .tabs-content");
          const viewportHeight = Math.max(2200, Math.min(maxViewportHeight, Math.ceil(box.y + box.height + 50)));
          if (viewportHeight !== 2200) {
            await viewport.set({ width: 1920, height: viewportHeight });
            await tab.playwright.waitForTimeout(900);
            box = await contentBox(tab);
          }
          if (!box || box.width < 300 || box.height < 80) throw new Error("内容区尺寸异常");
          const clip = {
            x: Math.max(0, box.x),
            y: Math.max(0, box.y),
            width: Math.min(1920 - Math.max(0, box.x), box.width),
            height: Math.min(viewportHeight - Math.max(0, box.y), box.height),
          };
          const bytes = await tab.screenshot({ clip });
          const file = path.join(root, `${String(larkRow).padStart(3, "0")}-${creator.star_id}-${item.field}.png`);
          await fs.writeFile(file, bytes);
          const cell = `${columnLetter(columns.indexOf(item.column))}${larkRow}`;
          result.images[item.field] = { path: file, cell, bytes: bytes.length, ...clip };
          manifest.push({ row: larkRow, column: item.column, cell, path: file });
        } catch (error) {
          result.errors.push(`${item.field}:${String(error?.message || error).slice(0, 180)}`);
        }
      }
      results.push(result);
      await fs.writeFile(checkpointPath, JSON.stringify(results, null, 2));
      await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2));
      await onProgress({ completed: index + 1, total: records.length, result });
    }
  } finally {
    await viewport.reset();
  }

  if (results.some((result) => result.errors.length)) throw new Error("能力截图存在失败项，请从 checkpoint 续跑失败项");
  return { results, manifest, checkpointPath, manifestPath };
}
