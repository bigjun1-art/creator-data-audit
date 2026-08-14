#!/usr/bin/env python3
"""Serially upload cell images to an existing Feishu sheet and verify image counts."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import Counter
from pathlib import Path


def cli(*args: str) -> dict:
    env = {**os.environ, "LARKSUITE_CLI_NO_UPDATE_NOTIFIER": "1", "LARKSUITE_CLI_NO_SKILLS_NOTIFIER": "1"}
    proc = subprocess.run(["lark-cli", *args, "--format", "json"], text=True, capture_output=True, env=env)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spreadsheet-token", required=True)
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    status = subprocess.run(
        ["lark-cli", "auth", "status", "--json", "--verify"], text=True, capture_output=True,
        env={**os.environ, "LARKSUITE_CLI_NO_UPDATE_NOTIFIER": "1", "LARKSUITE_CLI_NO_SKILLS_NOTIFIER": "1"},
    )
    if status.returncode:
        raise RuntimeError(status.stderr.strip() or status.stdout.strip())
    auth = json.loads(status.stdout)
    user = auth.get("identities", {}).get("user", {})
    if not user.get("verified") or user.get("tokenStatus") != "valid":
        raise RuntimeError("飞书用户身份未通过核验")

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    progress_path = out / "image-upload-progress.json"
    progress = json.loads(progress_path.read_text("utf-8")) if progress_path.exists() else {"completed": [], "failed": []}
    completed = set(progress["completed"])
    items = []
    for manifest in args.manifest:
        items.extend(json.loads(Path(manifest).read_text("utf-8")))
    if not items or any(not item.get("cell") for item in items):
        raise ValueError("manifest 必须包含非空 cell 和 path")

    for item in items:
        image = Path(item["path"]).resolve()
        key = f"{item['cell']}|{image}"
        if key in completed:
            continue
        if not image.exists():
            raise FileNotFoundError(image)
        relative = os.path.relpath(image, Path.cwd())
        cli(
            "sheets", "+cells-set-image", "--as", "user",
            "--spreadsheet-token", args.spreadsheet_token, "--sheet-id", args.sheet_id,
            "--range", item["cell"], "--image", relative,
        )
        completed.add(key)
        progress_path.write_text(json.dumps({"completed": sorted(completed), "failed": []}, ensure_ascii=False, indent=2), "utf-8")

    expected = Counter(item["cell"].rstrip("0123456789") for item in items)
    rows = [int("".join(ch for ch in item["cell"] if ch.isdigit())) for item in items]
    actual = {}
    for column, count in expected.items():
        response = cli(
            "sheets", "+cells-get", "--as", "user",
            "--spreadsheet-token", args.spreadsheet_token, "--sheet-id", args.sheet_id,
            "--range", f"{column}{min(rows)}:{column}{max(rows)}",
        )
        cells = response.get("data", {}).get("ranges", [{}])[0].get("cells", [])
        actual[column] = sum(
            any(piece.get("type") == "embed-image" for piece in (row[0].get("rich_text") or []))
            for row in cells if row
        )
        if actual[column] != count:
            raise RuntimeError(f"图片回读数量不一致: {column} expected={count} actual={actual[column]}")
    result = {"ok": True, "uploaded": len(items), "expected": dict(expected), "actual": actual}
    (out / "image-upload-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
