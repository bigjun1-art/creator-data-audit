#!/usr/bin/env python3
"""Prepare a parameterized creator-audit run and emit one Xingtu page runner."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


DEFAULT_COLUMNS = [
    "地区", "达人名称", "原表达人ID", "粉丝", "费用", "星图ID", "星图粉丝数",
    "达人类型", "内容主题", "创作能力-播放量（截图）", "最低播放量",
    "最高播放量", "平均播放量", "查询状态", "活动", "原表来源",
    "达人概览", "商业能力", "创作能力", "履约能力", "连接用户",
]

ALIASES = {
    "name": ["达人名称", "达人昵称", "达人", "昵称", "名称"],
    "creator_id": ["原表达人ID", "达人ID", "抖音号", "抖音ID", "账号ID", "ID"],
    "followers": ["粉丝", "粉丝数", "原表粉丝"],
    "fee": ["费用", "报价", "达人费用"],
    "campaign": ["活动", "项目", "场次"],
}

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def norm(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]", "", str(value or "")).lower()


def select_header(rows: list[list[object]]) -> tuple[int, dict[str, int]]:
    for index, row in enumerate(rows[:20]):
        normalized = {norm(value): col for col, value in enumerate(row) if value not in (None, "")}
        mapping: dict[str, int] = {}
        for key, names in ALIASES.items():
            for name in names:
                if norm(name) in normalized:
                    mapping[key] = normalized[norm(name)]
                    break
        if "name" in mapping:
            return index, mapping
    raise ValueError("未找到达人名称/达人昵称表头")


def cell_column(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference.upper())
    if not letters:
        return 0
    value = 0
    for char in letters.group(0):
        value = value * 26 + ord(char) - 64
    return value - 1


def load_xlsx_stdlib(path: Path, sheet_name: str | None) -> tuple[str, list[list[object]]]:
    with zipfile.ZipFile(path) as book:
        shared = []
        if "xl/sharedStrings.xml" in book.namelist():
            root = ET.fromstring(book.read("xl/sharedStrings.xml"))
            shared = ["".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t")) for item in root.findall(f"{{{MAIN_NS}}}si")]
        workbook = ET.fromstring(book.read("xl/workbook.xml"))
        rels = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels.findall(f"{{{PKG_REL_NS}}}Relationship")}
        sheets = workbook.find(f"{{{MAIN_NS}}}sheets")
        if sheets is None:
            raise ValueError("Excel 文件没有工作表")
        entries = list(sheets)
        selected = next((item for item in entries if item.attrib.get("name") == sheet_name), None) if sheet_name else entries[0]
        if selected is None:
            raise ValueError(f"找不到工作表: {sheet_name}")
        target = targets[selected.attrib[f"{{{REL_NS}}}id"]]
        sheet_path = "xl/" + target.lstrip("/").removeprefix("xl/")
        root = ET.fromstring(book.read(sheet_path))
        rows = []
        for row_node in root.findall(f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row"):
            values: list[object] = []
            for cell in row_node.findall(f"{{{MAIN_NS}}}c"):
                column = cell_column(cell.attrib.get("r", "A1"))
                while len(values) <= column:
                    values.append("")
                kind = cell.attrib.get("t")
                value_node = cell.find(f"{{{MAIN_NS}}}v")
                if kind == "inlineStr":
                    values[column] = "".join(node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t"))
                elif value_node is None:
                    values[column] = ""
                elif kind == "s":
                    values[column] = shared[int(value_node.text or 0)]
                elif kind == "b":
                    values[column] = value_node.text == "1"
                else:
                    raw = value_node.text or ""
                    try:
                        number = float(raw)
                        values[column] = int(number) if number.is_integer() else number
                    except ValueError:
                        values[column] = raw
            rows.append(values)
        return selected.attrib.get("name", path.stem), rows


def load_rows(path: Path, sheet_name: str | None) -> tuple[str, list[list[object]]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return path.stem, list(csv.reader(handle))
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("仅支持 .xlsx/.xlsm/.csv")
    try:
        import openpyxl
    except ImportError:
        return load_xlsx_stdlib(path, sheet_name)
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = book[sheet_name] if sheet_name else book.active
    return sheet.title, [list(row) for row in sheet.iter_rows(values_only=True)]


def value(row: list[object], mapping: dict[str, int], key: str) -> object:
    index = mapping.get(key)
    return "" if index is None or index >= len(row) or row[index] is None else row[index]


def identifier_text(raw: object) -> str:
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))
    return str(raw or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--sheet")
    parser.add_argument("--columns-json")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--retry-limit", type=int, default=2)
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence").mkdir(exist_ok=True)
    sheet_name, rows = load_rows(source, args.sheet)
    header_index, mapping = select_header(rows)
    inferred_campaign = ""
    if "campaign" not in mapping and header_index > 0:
        inferred_campaign = str(next((cell for cell in rows[header_index - 1] if str(cell or "").strip()), "")).strip()
    records = []
    for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        name = str(value(row, mapping, "name")).strip()
        if not name:
            continue
        creator_id = identifier_text(value(row, mapping, "creator_id"))
        records.append({
            "source_row": offset,
            "source_name": name,
            "source_creator_id": creator_id,
            "source_followers": value(row, mapping, "followers"),
            "source_fee": value(row, mapping, "fee"),
            "campaign": str(value(row, mapping, "campaign")).strip() or inferred_campaign,
            "source_file": source.name,
            "source_sheet": sheet_name,
        })
    if not records:
        raise ValueError("源表没有达人记录")
    id_counts = Counter(r["source_creator_id"] for r in records if r["source_creator_id"])
    duplicate_ids = sorted(key for key, count in id_counts.items() if count > 1)
    if duplicate_ids:
        raise ValueError(f"原达人ID重复: {duplicate_ids}")

    columns = DEFAULT_COLUMNS
    if args.columns_json:
        payload = json.loads(Path(args.columns_json).read_text("utf-8"))
        columns = payload["columns"] if isinstance(payload, dict) else payload
    columns = ["地区", *[column for column in columns if column != "地区"]]
    config = {
        "schema_version": 1,
        "platform": "xingtu",
        "source": str(source),
        "source_sheet": sheet_name,
        "record_count": len(records),
        "batch_size": max(1, min(args.batch_size, 10)),
        "retry_limit": max(0, min(args.retry_limit, 5)),
        "columns": columns,
        "checkpoint": str(out / "xingtu-capture.json"),
        "output_dir": str(out),
        "delivery_mode": "return",
    }
    (out / "source-records.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), "utf-8")
    (out / "run-config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), "utf-8")
    template = (Path(__file__).with_name("xingtu_page_runner.template.js")).read_text("utf-8")
    runner_input = {"config": config, "records": records}
    runner = template.replace("__CREATOR_AUDIT_INPUT_JSON__", json.dumps(runner_input, ensure_ascii=False))
    (out / "xingtu-page-runner.js").write_text(runner, "utf-8")
    bridge = Path(__file__).with_name("xingtu_chrome_bridge.mjs").resolve().as_uri()
    job = (
        f'import {{ runXingtuChromeAudit }} from {json.dumps(bridge)};\n'
        f'export default async function run(chrome) {{\n'
        f'  return runXingtuChromeAudit({{ chrome, runDir: {json.dumps(str(out))} }});\n'
        f'}}\n'
    )
    (out / "chrome-job.mjs").write_text(job, "utf-8")
    print(json.dumps({
        "ok": True,
        "records": len(records),
        "source_sheet": sheet_name,
        "columns": len(columns),
        "runner": str(out / "xingtu-page-runner.js"),
        "chrome_job": str(out / "chrome-job.mjs"),
        "checkpoint": config["checkpoint"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
