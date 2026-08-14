#!/usr/bin/env python3
"""Discover the newest completed creator-audit header through lark-cli (read-only)."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
from pathlib import Path


FATAL_AUTH = ("operation not permitted", "20064", "20073")
REQUIRED = {"达人名称", "星图ID", "查询状态"}


def run_cli(*args: str) -> dict:
    env = dict(os.environ)
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    output_flag = ["--json"] if args[:2] == ("auth", "status") else ["--format", "json"]
    proc = subprocess.run(["lark-cli", *args, *output_flag], text=True, capture_output=True, env=env)
    combined = (proc.stdout + "\n" + proc.stderr).strip()
    lowered = combined.lower()
    if any(code in lowered for code in FATAL_AUTH):
        raise RuntimeError("飞书凭据执行环境不可用；停止，不清理令牌、不重新授权：" + combined[-500:])
    if proc.returncode != 0:
        raise RuntimeError(combined[-1000:])
    return json.loads(proc.stdout)


def user_auth_ok(payload: dict) -> bool:
    data = payload.get("data", payload)
    identities = data.get("identities", {})
    user = identities.get("user", {})
    return bool(user.get("verified")) and user.get("tokenStatus") == "valid"


def parse_annotated_csv(text: str) -> list[list[str]]:
    clean = []
    for line in text.splitlines():
        if line.startswith("[row=") and "] " in line:
            clean.append(line.split("] ", 1)[1])
    return list(csv.reader(io.StringIO("\n".join(clean))))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--query", default="达人价值核查")
    args = parser.parse_args()
    auth = run_cli("auth", "status", "--verify")
    if not user_auth_ok(auth):
        raise RuntimeError("飞书用户身份未验证或 tokenStatus 不是 valid；停止，不重复授权")
    search = run_cli("drive", "+search", "--as", "user", "--query", args.query, "--only-title", "--doc-types", "sheet")
    workbooks = []
    for result in search.get("data", {}).get("results", []):
        meta = result.get("result_meta", {})
        if meta.get("token"):
            workbooks.append({"token": meta["token"], "updated": int(meta.get("update_time") or 0), "url": meta.get("url", "")})
    candidates = []
    for workbook in sorted(workbooks, key=lambda item: item["updated"], reverse=True)[:10]:
        info = run_cli("sheets", "+workbook-info", "--spreadsheet-token", workbook["token"])
        for sheet in info.get("data", {}).get("sheets", []):
            sample = run_cli("sheets", "+csv-get", "--spreadsheet-token", workbook["token"], "--sheet-id", sheet["sheet_id"], "--range", "A1:AZ5")
            rows = parse_annotated_csv(sample.get("data", {}).get("annotated_csv", ""))
            if not rows:
                continue
            header_index = next((index for index, row in enumerate(rows) if REQUIRED.issubset({cell.strip() for cell in row})), None)
            if header_index is None:
                continue
            headers = [cell.strip() for cell in rows[header_index]]
            data_rows = sum(any(cell.strip() for cell in row) for row in rows[header_index + 1:])
            if data_rows > 0:
                candidates.append({**workbook, "sheet_id": sheet["sheet_id"], "sheet_name": sheet["sheet_name"], "sheet_index": int(sheet.get("index") or 0), "header_row": header_index + 1, "columns": headers, "sample_data_rows": data_rows})
    if not candidates:
        raise RuntimeError("没有找到已完成且包含必要列的达人核查模板")
    selected = max(candidates, key=lambda item: (item["updated"], item["sheet_index"], item["sample_data_rows"], len(item["columns"])))
    target = Path(args.out).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(selected, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"ok": True, "columns": len(selected["columns"]), "sheet_name": selected["sheet_name"], "output": str(target)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
