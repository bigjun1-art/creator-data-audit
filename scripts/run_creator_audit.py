#!/usr/bin/env python3
"""Deterministic local orchestrator for creator-data-audit runs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent


def run_script(name: str, *args: str) -> dict:
    proc = subprocess.run([sys.executable, str(HERE / name), *args], text=True, capture_output=True)
    if proc.returncode:
        raise RuntimeError((proc.stdout + "\n" + proc.stderr).strip()[-2000:])
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    return json.loads(lines[-1]) if lines else {"ok": True}


def prepare(args: argparse.Namespace) -> dict:
    command = ["--source", args.source, "--out", args.out, "--batch-size", str(args.batch_size), "--retry-limit", str(args.retry_limit)]
    if args.sheet:
        command += ["--sheet", args.sheet]
    if args.columns_json:
        command += ["--columns-json", args.columns_json]
    result = run_script("prepare_run.py", *command)
    result["next_action"] = "在已初始化的 Chrome 绑定中导入 chrome-job.mjs，并调用 default(chrome) 一次"
    return result


def finish(args: argparse.Namespace) -> dict:
    root = Path(args.out).expanduser().resolve()
    browser_result = json.loads((root / "browser-result.json").read_text("utf-8"))
    if browser_result.get("ability_error"):
        raise RuntimeError("能力截图存在未完成项；重新调用 chrome-job.mjs 会从检查点续跑")
    validated = run_script(
        "validate_capture.py", "--capture", str(root / "xingtu-capture.json"),
        "--config", str(root / "run-config.json"), "--out", str(root),
    )
    evidence = run_script(
        "make_evidence_charts.py", "--results", str(root / "normalized-results.json"),
        "--out", str(root / "evidence"),
    )
    result = {"ok": True, "validated": validated, "evidence": evidence, "published": False}
    if args.folder_token or args.title:
        if not (args.folder_token and args.title):
            raise ValueError("发布飞书时 --folder-token 和 --title 必须同时提供")
        command = [
            "--csv", str(root / "lark-values.csv"), "--folder-token", args.folder_token,
            "--title", args.title, "--sheet-name", args.sheet_name, "--out", str(root / "lark"),
            "--image-manifest", str(root / "evidence" / "image-manifest.json"),
        ]
        ability_manifest = root / "ability-screenshots" / "ability-image-manifest.json"
        if ability_manifest.exists():
            command += ["--image-manifest", str(ability_manifest)]
        if args.dry_run:
            command.append("--dry-run")
        result["lark"] = run_script("write_lark_sheet.py", *command)
        result["published"] = not args.dry_run
    return result


def status(args: argparse.Namespace) -> dict:
    root = Path(args.out).expanduser().resolve()
    names = [
        "run-config.json", "source-records.json", "chrome-job.mjs", "xingtu-capture.json",
        "browser-result.json", "normalized-results.json", "summary.json", "lark-values.csv",
        "evidence/image-manifest.json", "ability-screenshots/ability-image-manifest.json",
        "lark/lark-result.json",
    ]
    files = {name: (root / name).exists() for name in names}
    payload = {"ok": True, "out": str(root), "files": files}
    for name in ("browser-result.json", "summary.json", "lark/lark-result.json"):
        if (root / name).exists():
            payload[name] = json.loads((root / name).read_text("utf-8"))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="达人数据核查统一执行入口")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="解析原表并生成固定 Chrome 作业")
    p.add_argument("--source", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--sheet")
    p.add_argument("--columns-json")
    p.add_argument("--batch-size", type=int, default=5)
    p.add_argument("--retry-limit", type=int, default=2)
    p.set_defaults(func=prepare)
    f = sub.add_parser("finish", help="校验、出图并可选发布飞书")
    f.add_argument("--out", required=True)
    f.add_argument("--folder-token")
    f.add_argument("--title")
    f.add_argument("--sheet-name", default="达人价值核查")
    f.add_argument("--dry-run", action="store_true")
    f.set_defaults(func=finish)
    s = sub.add_parser("status", help="读取检查点与产物状态")
    s.add_argument("--out", required=True)
    s.set_defaults(func=status)
    args = parser.parse_args()
    print(json.dumps(args.func(args), ensure_ascii=False))


if __name__ == "__main__":
    main()
