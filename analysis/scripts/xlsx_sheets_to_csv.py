#!/usr/bin/env python3
"""
Convert Excel workbooks into CSV files without external dependencies.

Usage:
- pass a single `.xlsx` file to export each worksheet into its own CSV
- pass a directory to convert every `.xlsx` file inside it

Excel lock files such as `~$Workbook.xlsx` are skipped automatically.
"""

from __future__ import annotations

import argparse
import csv
import posixpath
import re
import zipfile
from datetime import datetime, time, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"main": MAIN_NS, "pkg": PKG_REL_NS}

BUILTIN_DATE_FORMAT_IDS = {
    14, 15, 16, 17, 18, 19, 20, 21, 22,
    27, 28, 29, 30, 31, 32, 33, 34, 35, 36,
    45, 46, 47,
    50, 51, 52, 53, 54, 55, 56, 57, 58,
    71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81,
}

EXCEL_EPOCH = datetime(1899, 12, 30)


def sanitize_filename(name: str) -> str:
    """Make worksheet names safe for filenames."""
    cleaned = re.sub(r'[\\/*?:"<>|]', "_", name)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    return cleaned or "sheet"


def is_excel_lock_file(path: Path) -> bool:
    return path.name.startswith("~$")


def normalize_zip_path(base_dir: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(base_dir, target))


def extract_string_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(node.text or "" for node in element.findall(".//main:t", NS))


def parse_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return []

    root = ET.fromstring(archive.read(path))
    return [extract_string_text(item) for item in root.findall("main:si", NS)]


def looks_like_date_format(format_code: str) -> bool:
    code = format_code.lower()
    code = re.sub(r'"[^"]*"', "", code)
    code = re.sub(r"\\.", "", code)
    code = re.sub(r"_.", "", code)
    code = re.sub(r"\*.", "", code)
    code = re.sub(r"\[(?![hms]+\])[^]]+\]", "", code)

    if "am/pm" in code or "a/p" in code:
        return True

    return any(token in code for token in ("y", "d", "h", "s"))


def parse_date_styles(archive: zipfile.ZipFile) -> set[int]:
    path = "xl/styles.xml"
    if path not in archive.namelist():
        return set()

    root = ET.fromstring(archive.read(path))

    custom_formats: dict[int, str] = {}
    numfmts = root.find("main:numFmts", NS)
    if numfmts is not None:
        for numfmt in numfmts.findall("main:numFmt", NS):
            numfmt_id = numfmt.get("numFmtId")
            format_code = numfmt.get("formatCode")
            if numfmt_id is None or format_code is None:
                continue
            custom_formats[int(numfmt_id)] = format_code

    date_style_ids: set[int] = set()
    cell_xfs = root.find("main:cellXfs", NS)
    if cell_xfs is None:
        return date_style_ids

    for style_index, xf in enumerate(cell_xfs.findall("main:xf", NS)):
        numfmt_id = xf.get("numFmtId")
        if numfmt_id is None:
            continue

        fmt_id = int(numfmt_id)
        if fmt_id in BUILTIN_DATE_FORMAT_IDS:
            date_style_ids.add(style_index)
            continue

        format_code = custom_formats.get(fmt_id)
        if format_code and looks_like_date_format(format_code):
            date_style_ids.add(style_index)

    return date_style_ids


def load_sheet_targets(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))

    targets_by_id: dict[str, str] = {}
    for relation in relationships_root.findall(f"{{{PKG_REL_NS}}}Relationship"):
        relation_id = relation.get("Id")
        target = relation.get("Target")
        if relation_id and target:
            targets_by_id[relation_id] = normalize_zip_path("xl", target)

    sheets: list[tuple[str, str]] = []
    sheets_root = workbook_root.find("main:sheets", NS)
    if sheets_root is None:
        return sheets

    for sheet in sheets_root.findall("main:sheet", NS):
        name = sheet.get("name", "Sheet")
        relation_id = sheet.get(f"{{{DOC_REL_NS}}}id")
        if relation_id is None:
            continue

        target = targets_by_id.get(relation_id)
        if target:
            sheets.append((name, target))

    return sheets


def cell_ref_to_column_index(cell_ref: str | None) -> int:
    if not cell_ref:
        return 0

    column_letters = []
    for char in cell_ref:
        if char.isalpha():
            column_letters.append(char.upper())
        else:
            break

    index = 0
    for char in column_letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index


def max_columns_from_dimension(sheet_root: ET.Element) -> int:
    dimension = sheet_root.find("main:dimension", NS)
    if dimension is None:
        return 0

    ref = dimension.get("ref")
    if not ref:
        return 0

    end_ref = ref.split(":")[-1]
    return cell_ref_to_column_index(end_ref)


def format_excel_date(raw_value: str) -> str:
    try:
        serial = float(raw_value)
    except (TypeError, ValueError):
        return raw_value

    value = EXCEL_EPOCH + timedelta(days=serial)
    rounded = round(serial)
    if abs(serial - rounded) < 1e-10:
        return value.date().isoformat()

    if value.date() == EXCEL_EPOCH.date():
        return value.time().replace(microsecond=0).isoformat()

    if value.time() == time(0, 0):
        return value.date().isoformat()

    return value.replace(microsecond=0).isoformat(sep=" ")


def read_cell_value(
    cell: ET.Element,
    shared_strings: list[str],
    date_style_ids: set[int],
) -> str:
    cell_type = cell.get("t")
    style_id = int(cell.get("s", "0"))

    if cell_type == "inlineStr":
        return extract_string_text(cell.find("main:is", NS))

    value_element = cell.find("main:v", NS)
    raw_value = value_element.text if value_element is not None else ""

    if cell_type == "s":
        if not raw_value:
            return ""
        index = int(raw_value)
        return shared_strings[index] if 0 <= index < len(shared_strings) else ""

    if cell_type == "b":
        return "TRUE" if raw_value == "1" else "FALSE"

    if cell_type in {"str", "e", "d"}:
        return raw_value or ""

    if not raw_value:
        return ""

    if style_id in date_style_ids:
        return format_excel_date(raw_value)

    return raw_value


def iter_sheet_rows(
    archive: zipfile.ZipFile,
    sheet_path: str,
    shared_strings: list[str],
    date_style_ids: set[int],
) -> list[list[str]]:
    sheet_root = ET.fromstring(archive.read(sheet_path))
    sheet_data = sheet_root.find("main:sheetData", NS)
    if sheet_data is None:
        return []

    row_elements = sheet_data.findall("main:row", NS)
    max_columns = max_columns_from_dimension(sheet_root)
    for row in row_elements:
        for cell in row.findall("main:c", NS):
            max_columns = max(max_columns, cell_ref_to_column_index(cell.get("r")))

    rows: list[list[str]] = []
    last_row_number = 0

    for row in row_elements:
        row_number = int(row.get("r", str(last_row_number + 1)))
        while last_row_number + 1 < row_number:
            rows.append([""] * max_columns)
            last_row_number += 1

        values = [""] * max_columns
        for cell in row.findall("main:c", NS):
            column_index = cell_ref_to_column_index(cell.get("r"))
            if column_index <= 0:
                continue
            values[column_index - 1] = read_cell_value(cell, shared_strings, date_style_ids)

        rows.append(values)
        last_row_number = row_number

    return rows


def write_sheet_csv(
    archive: zipfile.ZipFile,
    sheet_path: str,
    csv_path: Path,
    shared_strings: list[str],
    date_style_ids: set[int],
) -> None:
    rows = iter_sheet_rows(archive, sheet_path, shared_strings, date_style_ids)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)

    print(f"Saved: {csv_path}")


def resolve_output_dir(input_path: Path, workbook_path: Path, output_dir: Path | None) -> Path:
    if output_dir is None:
        return workbook_path.with_suffix("")

    if input_path.is_dir():
        return output_dir / workbook_path.stem

    return output_dir


def convert_workbook(
    workbook_path: Path,
    destination_dir: Path,
) -> int:
    destination_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(workbook_path) as archive:
            shared_strings = parse_shared_strings(archive)
            date_style_ids = parse_date_styles(archive)
            sheets = load_sheet_targets(archive)

            if not sheets:
                raise ValueError("No worksheets found in workbook.")

            for index, (sheet_name, sheet_path) in enumerate(sheets, start=1):
                filename = f"{index:02d}_{sanitize_filename(sheet_name)}.csv"
                write_sheet_csv(
                    archive=archive,
                    sheet_path=sheet_path,
                    csv_path=destination_dir / filename,
                    shared_strings=shared_strings,
                    date_style_ids=date_style_ids,
                )
            return len(sheets)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"'{workbook_path}' is not a valid .xlsx file.") from exc


def find_workbooks(input_path: Path) -> list[Path]:
    if not input_path.exists():
        raise FileNotFoundError(f"Path not found: {input_path}")

    if input_path.is_file():
        if input_path.suffix.lower() != ".xlsx":
            raise ValueError("Input file must have a .xlsx extension.")
        if is_excel_lock_file(input_path):
            raise ValueError(f"Refusing to read Excel lock file: {input_path.name}")
        return [input_path]

    if input_path.is_dir():
        workbooks = sorted(
            path
            for path in input_path.iterdir()
            if path.is_file()
            and path.suffix.lower() == ".xlsx"
            and not is_excel_lock_file(path)
        )
        if not workbooks:
            raise ValueError(f"No .xlsx files found in directory: {input_path}")
        return workbooks

    raise ValueError(f"Unsupported path: {input_path}")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert one .xlsx file, or all .xlsx files in a directory, to CSV."
    )
    parser.add_argument(
        "input_path",
        help="Path to a .xlsx file or a directory containing .xlsx files",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory. Directory input creates one subdirectory per workbook.",
    )
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    input_path = Path(args.input_path).expanduser()
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else None

    try:
        workbooks = find_workbooks(input_path)
        total_sheets = 0

        for workbook in workbooks:
            destination_dir = resolve_output_dir(input_path, workbook, output_dir)
            print(f"Converting: {workbook}")
            sheet_count = convert_workbook(workbook, destination_dir)
            total_sheets += sheet_count

        workbook_count = len(workbooks)
        workbook_label = "workbook" if workbook_count == 1 else "workbooks"
        sheet_label = "sheet" if total_sheets == 1 else "sheets"
        print(f"Converted {workbook_count} {workbook_label} and {total_sheets} {sheet_label}.")
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
