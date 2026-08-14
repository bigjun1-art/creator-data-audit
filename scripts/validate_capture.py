#!/usr/bin/env python3
"""Validate Xingtu capture output and build rows for the latest Feishu schema."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path


def parse_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
    except Exception:
        return value[:10] if value else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    capture = json.loads(Path(args.capture).read_text("utf-8"))
    config = json.loads(Path(args.config).read_text("utf-8"))
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    results = capture.get("results", [])
    expected = int(config["record_count"])
    if len(results) != expected:
        raise ValueError(f"记录数不守恒: expected={expected}, actual={len(results)}")
    seen = set()
    normalized = []
    for result in results:
        key = result.get("source_creator_id") or f"name:{result.get('source_name')}"
        if key in seen:
            raise ValueError(f"重复结果: {key}")
        seen.add(key)
        items = result.get("items") or []
        plays = [int(item.get("play") or 0) for item in items]
        status = result.get("status")
        if status == "verified":
            if not result.get("star_id") or not result.get("platform_name"):
                raise ValueError(f"已核验记录缺少身份字段: {key}")
            query_status = (
                f"已核验：平台昵称{result['platform_name']}；原达人ID "
                f"{result.get('source_creator_id') or '原表未提供'} 与主页ID匹配；抓取时间 {parse_date(result.get('captured_at', ''))}"
            )
        elif status in {"not_matched", "ambiguous"}:
            candidates = "、".join(
                f"{item.get('nick_name', '')}/{item.get('unique_id') or item.get('short_id') or item.get('star_id', '')}"
                for item in result.get("candidates", [])[:5]
            )
            query_status = f"未唯一匹配：名称与原达人ID未同时匹配" + (f"；候选 {candidates}" if candidates else "；无有效候选")
        else:
            query_status = f"请求失败待重试：{result.get('error', '未返回错误详情')}"
        normalized.append({
            **result,
            "min_play": min(plays) if plays else None,
            "max_play": max(plays) if plays else None,
            "avg_play": round(sum(plays) / len(plays)) if plays else None,
            "query_status": query_status,
            "playback_image": "",
            "overview_image": "",
            "commercial_image": "",
            "creative_image": "",
            "contract_image": "",
            "connect_image": "",
        })
    counts = {
        "total": len(normalized),
        "verified": sum(row.get("status") == "verified" for row in normalized),
        "ambiguous": sum(row.get("status") in {"not_matched", "ambiguous"} for row in normalized),
        "failed": sum(row.get("status") == "request_failed" for row in normalized),
    }
    if counts["total"] != counts["verified"] + counts["ambiguous"] + counts["failed"]:
        raise ValueError(f"状态计数不守恒: {counts}")
    (out / "normalized-results.json").write_text(json.dumps(normalized, ensure_ascii=False, indent=2), "utf-8")
    (out / "summary.json").write_text(json.dumps(counts, ensure_ascii=False, indent=2), "utf-8")

    columns = config["columns"]
    field_map = {
        "地区": lambda r: r.get("region", "") if r.get("status") == "verified" else "",
        "达人名称": lambda r: r.get("platform_name") if r.get("status") == "verified" else r.get("source_name"),
        "原表达人ID": lambda r: r.get("source_creator_id", ""),
        "粉丝": lambda r: r.get("source_followers", ""),
        "费用": lambda r: r.get("source_fee", ""),
        "星图ID": lambda r: r.get("star_id", "") if r.get("status") == "verified" else "",
        "星图粉丝数": lambda r: r.get("star_followers", "") if r.get("status") == "verified" else "",
        "达人类型": lambda r: "、".join(r.get("author_type") or []) if r.get("status") == "verified" else "",
        "内容主题": lambda r: "、".join(r.get("content_themes") or []) if r.get("status") == "verified" else "",
        "创作能力-播放量（截图）": lambda r: "",
        "最低播放量": lambda r: r.get("min_play", "") if r.get("status") == "verified" else "",
        "最高播放量": lambda r: r.get("max_play", "") if r.get("status") == "verified" else "",
        "平均播放量": lambda r: r.get("avg_play", "") if r.get("status") == "verified" else "",
        "查询状态": lambda r: r.get("query_status", ""),
        "活动": lambda r: r.get("campaign", ""),
        "原表来源": lambda r: r.get("source_file", ""),
        "达人概览": lambda r: "",
        "商业能力": lambda r: "",
        "创作能力": lambda r: "",
        "履约能力": lambda r: "",
        "连接用户": lambda r: "",
    }
    missing = [column for column in columns if column not in field_map]
    if missing:
        raise ValueError(f"最新版列尚未配置字段映射: {missing}")
    with (out / "lark-values.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in normalized:
            writer.writerow([field_map[column](row) for column in columns])
    print(json.dumps({"ok": True, **counts, "normalized": str(out / "normalized-results.json"), "csv": str(out / "lark-values.csv")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
