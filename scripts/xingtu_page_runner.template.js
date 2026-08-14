(async () => {
  "use strict";
  const input = __CREATOR_AUDIT_INPUT_JSON__;
  const cfg = input.config;
  const records = input.records;
  if (location.hostname !== "www.xingtu.cn") throw new Error("请在已登录的 www.xingtu.cn 页面运行");

  const SEARCH_PATH = "/gw/api/gsearch/search_for_author_square";
  const BASE_PATH = "/gw/api/author/get_author_base_info";
  const ITEMS_PATH = "/gw/api/author/get_author_latest_items";
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const norm = (value) => String(value ?? "").replace(/[^A-Za-z0-9\u4e00-\u9fff]/g, "").toLowerCase();
  const aliases = (name) => [...new Set([String(name || ""), String(name || "").split("（")[0]])].filter(Boolean);
  const parseLossless = (text) => JSON.parse(text.replace(/([:\[,]\s*)(-?\d{16,})(?=\s*[,}\]])/g, '$1"$2"'));
  const unwrap = (payload) => payload && payload.data && typeof payload.data === "object" ? payload.data : payload;

  async function requestJson(path, options = {}) {
    let lastError;
    for (let attempt = 0; attempt <= cfg.retry_limit; attempt += 1) {
      try {
        const response = await fetch(path, {credentials: "include", ...options});
        const text = await response.text();
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${text.slice(0, 160)}`);
        const payload = unwrap(parseLossless(text));
        const baseResp = payload?.base_resp || payload?.BaseResp;
        if (baseResp && Number(baseResp.status_code ?? baseResp.StatusCode ?? 0) !== 0) {
          throw new Error(String(baseResp.status_message || baseResp.StatusMessage || "平台返回失败"));
        }
        return payload;
      } catch (error) {
        lastError = error;
        if (attempt < cfg.retry_limit) await sleep(700 * (attempt + 1));
      }
    }
    throw lastError;
  }

  async function search(keyword) {
    const body = {
      scene_param: {platform_source: 1, search_scene: 1, display_scene: 1, task_category: 1, marketing_target: 1, first_industry_id: 0},
      page_param: {page: "1", limit: "20"},
      sort_param: {sort_field: {field_name: "score"}, sort_type: 2},
      search_param: {seach_type: 2, keyword, is_new_nickname_query: true},
    };
    return requestJson(SEARCH_PATH, {method: "POST", headers: {"content-type": "application/json", "agw-js-conv": "str", "x-login-source": "1"}, body: JSON.stringify(body)});
  }

  async function baseInfo(starId) {
    const query = new URLSearchParams({o_author_id: starId, platform_source: "1", platform_channel: "1", recommend: "true", need_sec_uid: "true", need_linkage_info: "true"});
    return requestJson(`${BASE_PATH}?${query}`);
  }

  async function latestItems(starId) {
    const query = new URLSearchParams({o_author_id: starId, platform_source: "1", platform_channel: "1", limit: "15"});
    return requestJson(`${ITEMS_PATH}?${query}`);
  }

  function candidateId(author) {
    const attrs = author?.attribute_datas || author?.attributeDatas || author || {};
    return String(attrs.id || author?.star_id || author?.starId || "");
  }

  function identityMatches(record, base) {
    const nameOk = aliases(record.source_name).some((name) => norm(name) === norm(base?.nick_name));
    if (!nameOk) return false;
    if (!record.source_creator_id) return true;
    const sourceId = norm(record.source_creator_id);
    return [base?.unique_id, base?.short_id].some((value) => norm(value) === sourceId);
  }

  function pickRegion(base) {
    return String(
      base?.city_name || base?.city || base?.region_name || base?.region ||
      base?.location || base?.area || base?.province_name || base?.province || ""
    ).trim();
  }

  async function auditOne(record) {
    const keywords = [...new Set([record.source_creator_id, record.source_name].filter(Boolean))];
    const seenIds = new Set();
    const candidates = [];
    const verifiedByStarId = new Map();
    for (const keyword of keywords) {
      const found = await search(keyword);
      for (const author of found?.authors || found?.author_list || []) {
        const attrs = author?.attribute_datas || author?.attributeDatas || author || {};
        if (!aliases(record.source_name).some((name) => norm(name) === norm(attrs.nick_name))) continue;
        const id = candidateId(author);
        if (!id || seenIds.has(id)) continue;
        seenIds.add(id);
        const base = await baseInfo(id);
        candidates.push({star_id: id, nick_name: base?.nick_name || "", unique_id: String(base?.unique_id || ""), short_id: String(base?.short_id || "")});
        if (identityMatches(record, base)) verifiedByStarId.set(id, {starId: id, base});
        await sleep(180);
      }
      if (verifiedByStarId.size === 1) break;
      await sleep(250);
    }
    const verified = [...verifiedByStarId.values()];
    if (verified.length !== 1) {
      return {...record, status: verified.length > 1 ? "ambiguous" : "not_matched", candidates, captured_at: new Date().toISOString()};
    }
    const {starId, base} = verified[0];
    const itemPayload = await latestItems(starId);
    const items = (itemPayload?.ltm_item_statics || itemPayload?.items || []).slice(0, 15).map((item) => ({
      item_id: String(item.item_id || item.id || ""),
      play: Number(item.play || 0),
      create_time: Number(item.create_time || 0),
      title: item.title || "",
    }));
    let tags = base?.tags || [];
    if (typeof tags === "string") { try { tags = JSON.parse(tags); } catch (_) { tags = []; } }
    return {
      ...record,
      status: "verified",
      platform_name: base?.nick_name || "",
      platform_creator_id: String(base?.unique_id || base?.short_id || ""),
      star_id: starId,
      star_followers: Number(base?.follower || 0),
      region: pickRegion(base),
      author_type: Array.isArray(tags) ? tags : [],
      content_themes: Array.isArray(base?.content_theme_labels) ? base.content_theme_labels : [],
      items,
      captured_at: new Date().toISOString(),
    };
  }

  function downloadJson(name, payload) {
    if (cfg.delivery_mode === "return") return;
    const anchor = document.createElement("a");
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], {type: "application/json"}));
    anchor.href = url;
    anchor.download = name;
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const state = {schema_version: 1, config: cfg, completed_ids: [], ambiguous_ids: [], failed_ids: [], results: [], started_at: new Date().toISOString()};
  for (let offset = 0; offset < records.length; offset += cfg.batch_size) {
    const batch = records.slice(offset, offset + cfg.batch_size);
    const batchResults = await Promise.all(batch.map(async (record) => {
      try {
        return await auditOne(record);
      } catch (error) {
        return {...record, status: "request_failed", error: String(error), captured_at: new Date().toISOString()};
      }
    }));
    for (const result of batchResults) {
      state.results.push(result);
      const key = result.source_creator_id || result.source_name;
      if (result.status === "verified") state.completed_ids.push(key);
      else if (result.status === "request_failed") state.failed_ids.push(key);
      else state.ambiguous_ids.push(key);
    }
    downloadJson(`creator-audit-checkpoint-${String(state.results.length).padStart(3, "0")}.json`, state);
    await sleep(800);
  }
  state.finished_at = new Date().toISOString();
  downloadJson("xingtu-capture.json", state);
  console.log("CREATOR_AUDIT_DONE", {total: records.length, verified: state.completed_ids.length, ambiguous: state.ambiguous_ids.length, failed: state.failed_ids.length});
  return state;
})()
