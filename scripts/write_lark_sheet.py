#!/usr/bin/env python3
"""Create a Feishu spreadsheet, upload cell images serially, and read back values."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
from pathlib import Path


FATAL_AUTH = ("operation not permitted", "20064", "20073")


def run_cli(*args: str, input_text: str | None = None) -> dict:
    env = dict(os.environ)
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    output_flag = ["--json"] if args[:2] == ("auth", "status") else ["--format", "json"]
    proc = subprocess.run(["lark-cli", *args, *output_flag], text=True, input=input_text, capture_output=True, env=env)
    combined = (proc.stdout + "\n" + proc.stderr).strip()
    lowered = combined.lower()
    if any(code in lowered for code in FATAL_AUTH):
        raise RuntimeError("飞书凭据执行环境不可用；停止，不清理令牌、不重新授权：" + combined[-500:])
    if proc.returncode != 0:
        raise RuntimeError(combined[-1200:])
    return json.loads(proc.stdout)


def find_key(value: object, names: set[str]) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in names and isinstance(child, str) and child:
                return child
            found = find_key(child, names)
            if found:
                return found
    if isinstance(value, list):
        for child in value:
            found = find_key(child, names)
            if found:
                return found
    return None


def auth_ok(payload: dict) -> bool:
    data = payload.get("data", payload)
    user = data.get("identities", {}).get("user", {})
    return bool(user.get("verified")) and user.get("tokenStatus") == "valid"


def col_letter(index: int) -> str:
    result = ""
    index += 1
    while index:
        index, remain = divmod(index - 1, 26)
        result = chr(65 + remain) + result
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--folder-token", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--sheet-name", default="达人价值核查")
    parser.add_argument("--image-manifest", action="append", default=[])
    parser.add_argument("--out", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with Path(args.csv).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if len(rows) < 2:
        raise ValueError("CSV 没有数据行")
    headers, data = rows[0], rows[1:]
    numeric_headers = {"最低播放量", "最高播放量", "平均播放量"}
    for row in data:
        for name in numeric_headers:
            if name in headers:
                index = headers.index(name)
                if index >= len(row) or not row[index].strip():
                    if index < len(row):
                        row[index] = None
                elif row[index].replace(",", "").isdigit():
                    row[index] = int(row[index].replace(",", ""))
                else:
                    raise ValueError(f"{name} 不是整数或空值: {row[index]}")
    payload = {
        "sheets": [{
            "name": args.sheet_name,
            "columns": headers,
            "data": data,
            "dtypes": {header: ("Int64" if header in numeric_headers else "object") for header in headers},
            "formats": {header: "#,##0" for header in headers if header in numeric_headers},
        }]
    }
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    payload_path = out / "lark-create-payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), "utf-8")
    if args.dry_run:
        print(json.dumps({"ok": True, "dry_run": True, "rows": len(data), "columns": len(headers), "payload": str(payload_path)}, ensure_ascii=False))
        return
    auth = run_cli("auth", "status", "--verify")
    if not auth_ok(auth):
        raise RuntimeError("飞书用户身份未验证或 tokenStatus 不是 valid；停止，不重复授权")
    created = run_cli("sheets", "+workbook-create", "--as", "user", "--folder-token", args.folder_token, "--title", args.title, "--sheets", "-", input_text=payload_path.read_text("utf-8"))
    token = find_key(created, {"spreadsheet_token", "spreadsheetToken"}) or find_key(created, {"token"})
    if not token:
        raise RuntimeError("创建成功响应中未找到 spreadsheet token")
    info = run_cli("sheets", "+workbook-info", "--spreadsheet-token", token)
    sheets = info.get("data", {}).get("sheets", [])
    sheet = next((item for item in sheets if item.get("sheet_name") == args.sheet_name), sheets[0] if sheets else None)
    if not sheet:
        raise RuntimeError("创建后没有找到工作表")
    sheet_id = sheet["sheet_id"]
    run_cli("sheets", "+dim-freeze", "--as", "user", "--spreadsheet-token", token, "--sheet-id", sheet_id, "--dimension", "row", "--count", "1")
    run_cli("sheets", "+cells-set-style", "--as", "user", "--spreadsheet-token", token, "--sheet-id", sheet_id, "--range", f"A1:{col_letter(len(headers)-1)}1", "--background-color", "#1F4E78", "--font-color", "#FFFFFF", "--font-weight", "bold", "--horizontal-alignment", "center", "--vertical-alignment", "middle", "--word-wrap", "auto-wrap")
    run_cli("sheets", "+rows-resize", "--as", "user", "--spreadsheet-token", token, "--sheet-id", sheet_id, "--range", "1", "--height", "44")
    run_cli("sheets", "+rows-resize", "--as", "user", "--spreadsheet-token", token, "--sheet-id", sheet_id, "--range", f"2:{len(rows)}", "--height", "140")
    width_by_header = {
        "地区": 110, "达人名称": 160, "原表达人ID": 130, "粉丝": 90, "费用": 90,
        "星图ID": 130, "星图粉丝数": 130, "达人类型": 180, "内容主题": 180,
        "创作能力-播放量（截图）": 300, "最低播放量": 105, "最高播放量": 105,
        "平均播放量": 105, "查询状态": 220, "活动": 220, "原表来源": 220,
        "达人概览": 300, "商业能力": 300, "创作能力": 300, "履约能力": 300, "连接用户": 300,
    }
    width_map = {col_letter(index): width_by_header.get(header, 140) for index, header in enumerate(headers)}
    run_cli("sheets", "+cols-resize", "--as", "user", "--spreadsheet-token", token, "--sheet-id", sheet_id, "--widths", json.dumps(width_map, ensure_ascii=False))

    manifests = []
    for manifest_path in args.image_manifest:
        manifests.extend(json.loads(Path(manifest_path).read_text("utf-8")))
    uploaded = 0
    for item in manifests:
        column = item["column"]
        path = Path(item["path"])
        if column not in headers or not path.exists():
            continue
        cell = f"{col_letter(headers.index(column))}{int(item['row'])}"
        image_arg = os.path.relpath(path, Path.cwd())
        run_cli("sheets", "+cells-set-image", "--as", "user", "--spreadsheet-token", token, "--sheet-id", sheet_id, "--range", cell, "--image", image_arg)
        uploaded += 1
    readback = run_cli("sheets", "+csv-get", "--spreadsheet-token", token, "--sheet-id", sheet_id, "--range", f"A1:{col_letter(len(headers)-1)}{len(rows)}")
    actual_range = readback.get("data", {}).get("actual_range", "")
    if not actual_range.endswith(str(len(rows))):
        raise RuntimeError(f"回读范围不完整: {actual_range}")
    result = {"ok": True, "spreadsheet_token": token, "sheet_id": sheet_id, "url": f"https://my.feishu.cn/sheets/{token}", "rows": len(data), "images": uploaded, "actual_range": actual_range}
    (out / "lark-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
