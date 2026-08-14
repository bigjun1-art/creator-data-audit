import fs from "node:fs/promises";
import path from "node:path";
import { captureAbilityScreenshots } from "./xingtu_ability_capture.mjs";

function isXingtu(url) {
  try { return new URL(String(url || "")).hostname === "www.xingtu.cn"; } catch (_) { return false; }
}

function recordKey(record) {
  return String(record?.source_creator_id || `name:${record?.source_name || ""}`);
}

async function readJson(file, fallback = null) {
  try { return JSON.parse(await fs.readFile(file, "utf8")); } catch (_) { return fallback; }
}

async function claimXingtuTab(chrome) {
  await chrome.nameSession("📊 巨量星图达人批量核查");
  for (const info of await chrome.tabs.list()) {
    if (isXingtu(info.url)) return chrome.tabs.get(info.id);
  }
  for (const info of await chrome.user.openTabs()) {
    if (isXingtu(info.url)) return chrome.user.claimTab(info);
  }
  const tab = await chrome.tabs.new();
  await tab.goto("https://www.xingtu.cn/ad/creator/market");
  return tab;
}

function runnerForRecords(source, records) {
  const needle = "const records = input.records;";
  if (!source.includes(needle)) throw new Error("星图执行器结构已变化，未找到 records 注入点");
  return source.replace(needle, `const records = ${JSON.stringify(records)};`);
}

function mergeResults(sourceRecords, previous, fresh) {
  const merged = new Map();
  for (const item of previous || []) merged.set(recordKey(item), item);
  for (const item of fresh || []) merged.set(recordKey(item), item);
  return sourceRecords.map((record) => merged.get(recordKey(record))).filter(Boolean);
}

export async function runXingtuChromeAudit({
  chrome,
  runDir,
  tab = null,
  captureAbilities = true,
  timeoutMs = 20 * 60 * 1000,
  finalize = true,
}) {
  if (!chrome) throw new Error("必须传入已按 Chrome Skill 初始化的 chrome 绑定");
  const root = path.resolve(runDir);
  const configPath = path.join(root, "run-config.json");
  const recordsPath = path.join(root, "source-records.json");
  const runnerPath = path.join(root, "xingtu-page-runner.js");
  const capturePath = path.join(root, "xingtu-capture.json");
  const resultPath = path.join(root, "browser-result.json");
  const config = await readJson(configPath);
  const sourceRecords = await readJson(recordsPath);
  if (!config || !Array.isArray(sourceRecords) || !sourceRecords.length) throw new Error("运行包不完整：缺少配置或达人记录");
  if (config.platform !== "xingtu") throw new Error(`浏览器桥接器不支持平台：${config.platform}`);
  const runnerSource = await fs.readFile(runnerPath, "utf8");
  const existing = await readJson(capturePath, { results: [] });
  const previous = Array.isArray(existing?.results) ? existing.results : [];
  const previousByKey = new Map(previous.map((item) => [recordKey(item), item]));
  const pending = sourceRecords.filter((record) => {
    const item = previousByKey.get(recordKey(record));
    return !item || item.status === "request_failed";
  });
  let activeTab = tab;
  let state = existing;
  let abilityError = "";
  try {
    activeTab = activeTab || await claimXingtuTab(chrome);
    if (!isXingtu(await activeTab.url())) await activeTab.goto("https://www.xingtu.cn/ad/creator/market");
    await activeTab.playwright.waitForLoadState({ state: "domcontentloaded", timeoutMs: 30000 });
    if (!isXingtu(await activeTab.url())) throw new Error("Google Chrome 中巨量星图未登录，请先在该浏览器完成登录");
    if (pending.length) {
      const batchState = await activeTab.playwright.evaluate(
        runnerForRecords(runnerSource, pending), undefined, { timeoutMs },
      );
      if (!batchState || !Array.isArray(batchState.results)) throw new Error("星图后台执行器未返回结构化结果");
      const merged = mergeResults(sourceRecords, previous, batchState.results);
      if (merged.length !== sourceRecords.length) throw new Error(`结果数不守恒：${merged.length}/${sourceRecords.length}`);
      state = { ...batchState, results: merged };
      state.completed_ids = merged.filter((x) => x.status === "verified").map(recordKey);
      state.ambiguous_ids = merged.filter((x) => ["not_matched", "ambiguous"].includes(x.status)).map(recordKey);
      state.failed_ids = merged.filter((x) => x.status === "request_failed").map(recordKey);
      await fs.writeFile(capturePath, JSON.stringify(state, null, 2));
    }
    if (!Array.isArray(state?.results) || state.results.length !== sourceRecords.length) throw new Error("后台结果尚未完成，不能进入截图阶段");
    const verified = state.results
      .map((item, index) => ({ ...item, lark_row: index + 2 }))
      .filter((item) => item.status === "verified");
    let ability = null;
    if (captureAbilities && verified.length) {
      try {
        ability = await captureAbilityScreenshots({
          chrome,
          tab: activeTab,
          records: verified,
          columns: config.columns,
          outDir: path.join(root, "ability-screenshots"),
          resume: true,
        });
        const regionByKey = new Map(ability.results.map((item) => [String(item.star_id), item.region]));
        state.results = state.results.map((item) => {
          const region = String(regionByKey.get(String(item.star_id)) || "").trim();
          return region && region !== "--" ? { ...item, region } : item;
        });
        await fs.writeFile(capturePath, JSON.stringify(state, null, 2));
      } catch (error) {
        abilityError = String(error?.message || error);
      }
    }
    const summary = {
      ok: !abilityError,
      total: state.results.length,
      verified: state.results.filter((x) => x.status === "verified").length,
      ambiguous: state.results.filter((x) => ["not_matched", "ambiguous"].includes(x.status)).length,
      failed: state.results.filter((x) => x.status === "request_failed").length,
      pending_before_run: pending.length,
      capture: capturePath,
      ability_manifest: path.join(root, "ability-screenshots", "ability-image-manifest.json"),
      ability_error: abilityError,
    };
    await fs.writeFile(resultPath, JSON.stringify(summary, null, 2));
    if (abilityError) throw new Error(`能力截图未完整完成：${abilityError}`);
    return summary;
  } finally {
    if (finalize) await chrome.tabs.finalize({ keep: [] });
  }
}
