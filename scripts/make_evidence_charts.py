#!/usr/bin/env python3
"""Generate dated recent-15-play evidence charts and an image upload manifest."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff_-]+", "_", value).strip("_") or "creator"


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
    ]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def chart(row: dict, path: Path) -> None:
    items = (row.get("items") or [])[:15]
    plays = [int(item.get("play") or 0) for item in items]
    dates = [
        datetime.fromtimestamp(int(item.get("create_time") or 0), ZoneInfo("Asia/Shanghai")).strftime("%m-%d")
        if item.get("create_time") else "--"
        for item in items
    ]
    width, height = 1200, 640
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font, body_font, small_font = font(30), font(18), font(14)
    name = row.get("platform_name") or row.get("source_name") or "达人"
    low = min(plays) if plays else 0
    high = max(plays) if plays else 0
    average = round(sum(plays) / len(plays)) if plays else 0
    date_range = f"{dates[-1]} 至 {dates[0]}" if dates else "无作品日期"
    draw.text((40, 24), f"{name}｜创作能力-播放量", fill="#202124", font=title_font)
    draw.text((40, 76), f"最新{len(plays)}条作品  最低 {low:,}  最高 {high:,}  平均 {average:,}", fill="#4b5563", font=body_font)
    draw.text((40, 110), f"作品日期范围：{date_range}｜星图ID：{row.get('star_id', '')}", fill="#6b7280", font=small_font)
    left, top, right, bottom = 70, 170, 1150, 550
    draw.line((left, bottom, right, bottom), fill="#cbd5e1", width=2)
    maximum = max(plays) if plays else 1
    step = (right - left) / max(1, len(plays))
    bar_width = max(18, int(step * 0.62))
    for index, play in enumerate(plays):
        x = left + index * step + (step - bar_width) / 2
        bar_height = (bottom - top) * play / maximum if maximum else 0
        draw.rounded_rectangle((x, bottom - bar_height, x + bar_width, bottom), radius=4, fill="#3296fa")
        label = f"{play / 10000:.1f}w" if play >= 10000 else str(play)
        label_width = draw.textbbox((0, 0), label, font=small_font)[2]
        draw.text((x + (bar_width - label_width) / 2, max(top, bottom - bar_height - 23)), label, fill="#475569", font=small_font)
        date_width = draw.textbbox((0, 0), dates[index], font=small_font)[2]
        draw.text((x + (bar_width - date_width) / 2, bottom + 12), dates[index], fill="#64748b", font=small_font)
    draw.text((40, 600), "数据来源：巨量星图创作能力页最近15条视频列表；横轴为作品发布日期（月-日）。", fill="#64748b", font=small_font)
    image.save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result_path = Path(args.results).expanduser().resolve()
    rows = json.loads(result_path.read_text("utf-8"))
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for index, row in enumerate(rows, start=2):
        if row.get("status") != "verified" or not row.get("items"):
            continue
        path = out / f"{index:03d}-{safe_name(row.get('platform_name') or row.get('source_name', ''))}-播放量.png"
        chart(row, path)
        row["playback_image"] = str(path)
        manifest.append({"row": index, "column": "创作能力-播放量（截图）", "path": str(path)})
    result_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")
    (out / "image-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"ok": True, "charts": len(manifest), "manifest": str(out / "image-manifest.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
