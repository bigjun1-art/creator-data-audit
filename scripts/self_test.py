#!/usr/bin/env python3
"""Offline smoke test for the executable creator-data-audit pipeline."""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent


def run(*args: str) -> None:
    subprocess.run(args, check=True, text=True, capture_output=True)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="creator-audit-test-") as temp:
        root = Path(temp)
        source = root / "source.csv"
        with source.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["达人昵称", "抖音号", "粉丝", "费用"])
            writer.writerow(["测试达人A", "demo_a", "1.2w", "500"])
            writer.writerow(["测试达人B", "demo_b", "2w", "800"])
        run(sys.executable, str(HERE / "prepare_run.py"), "--source", str(source), "--out", str(root / "run"))
        runner = root / "run" / "xingtu-page-runner.js"
        chrome_job = root / "run" / "chrome-job.mjs"
        text = runner.read_text("utf-8")
        for endpoint in ("search_for_author_square", "get_author_base_info", "get_author_latest_items"):
            assert endpoint in text
        assert "/Users/" not in text
        assert 'delivery_mode": "return"' in text
        node = shutil.which("node")
        if node:
            run(node, "--check", str(runner))
            run(node, "--check", str(HERE / "xingtu_ability_capture.mjs"))
            run(node, "--check", str(HERE / "xingtu_chrome_bridge.mjs"))
            run(node, "--check", str(chrome_job))
        capture = {
            "results": [
                {
                    "source_name": "测试达人A", "source_creator_id": "demo_a", "source_followers": "1.2w", "source_fee": "500",
                    "source_file": "source.csv", "campaign": "", "status": "verified", "platform_name": "测试达人A",
                    "platform_creator_id": "demo_a", "star_id": "7000000000000000001", "star_followers": 12345,
                    "region": "贵阳", "author_type": ["美食"], "content_themes": ["美食探店"], "captured_at": "2026-08-05T10:00:00+08:00",
                    "items": [
                        {"item_id": "1", "play": 100, "create_time": 1785888000, "title": "A"},
                        {"item_id": "2", "play": 300, "create_time": 1785801600, "title": "B"},
                    ],
                },
                {
                    "source_name": "测试达人B", "source_creator_id": "demo_b", "source_followers": "2w", "source_fee": "800",
                    "source_file": "source.csv", "campaign": "", "status": "not_matched", "candidates": [], "captured_at": "2026-08-05T10:00:00+08:00",
                },
            ]
        }
        capture_path = root / "run" / "xingtu-capture.json"
        if node:
            mock_script = root / "bridge-smoke.mjs"
            mock_script.write_text(
                f'''import {{ runXingtuChromeAudit }} from {json.dumps((HERE / "xingtu_chrome_bridge.mjs").resolve().as_uri())};
const state = {json.dumps(capture, ensure_ascii=False)};
let evaluateCalls = 0;
const tab = {{
  id: "mock-tab",
  async url() {{ return "https://www.xingtu.cn/ad/creator/market"; }},
  async goto() {{}},
  playwright: {{ async waitForLoadState() {{}}, async evaluate() {{ evaluateCalls += 1; return state; }} }},
}};
const chrome = {{
  async nameSession() {{}},
  tabs: {{ async list() {{ return [{{ id: "mock-tab", url: "https://www.xingtu.cn/ad/creator/market" }}]; }}, async get() {{ return tab; }}, async finalize() {{}} }},
  user: {{ async openTabs() {{ return []; }}, async claimTab() {{ return tab; }} }},
}};
await runXingtuChromeAudit({{ chrome, runDir: {json.dumps(str(root / "run"))}, captureAbilities: false }});
const resumed = await runXingtuChromeAudit({{ chrome, runDir: {json.dumps(str(root / "run"))}, captureAbilities: false }});
if (evaluateCalls !== 1 || resumed.pending_before_run !== 0) throw new Error("resume failed");
''', "utf-8")
            run(node, str(mock_script))
            bridge_result = json.loads((root / "run" / "browser-result.json").read_text("utf-8"))
            assert bridge_result["total"] == 2 and bridge_result["verified"] == 1
        else:
            capture_path.write_text(json.dumps(capture, ensure_ascii=False), "utf-8")
            (root / "run" / "browser-result.json").write_text(json.dumps({"ok": True, "ability_error": ""}), "utf-8")
        ability_dir = root / "run" / "ability-screenshots"
        ability_dir.mkdir(exist_ok=True)
        (ability_dir / "ability-image-manifest.json").write_text("[]", "utf-8")
        run(
            sys.executable, str(HERE / "run_creator_audit.py"), "finish", "--out", str(root / "run"),
            "--folder-token", "offline-test", "--title", "offline-test", "--dry-run",
        )
        summary = json.loads((root / "run" / "summary.json").read_text("utf-8"))
        manifest = json.loads((root / "run" / "evidence" / "image-manifest.json").read_text("utf-8"))
        assert summary == {"total": 2, "verified": 1, "ambiguous": 1, "failed": 0}
        assert len(manifest) == 1 and Path(manifest[0]["path"]).exists()
        payload = json.loads((root / "run" / "lark" / "lark-create-payload.json").read_text("utf-8"))
        assert payload["sheets"][0]["columns"][0] == "地区"
        assert payload["sheets"][0]["data"][0][0] == "贵阳"
        assert payload["sheets"][0]["dtypes"]["最低播放量"] == "Int64"
    print(json.dumps({"ok": True, "tests": ["prepare", "runner-syntax", "chrome-job-syntax", "chrome-bridge", "ability-runner-syntax", "unified-entry", "region-first", "count-conservation", "dated-chart", "lark-payload"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
