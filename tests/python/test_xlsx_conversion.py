"""Tests for the empirical-workbook to CSV conversion step.

The converter reads SpreadsheetML with the standard library rather than
openpyxl, so these tests build minimal workbooks by hand. That keeps the test
honest about the format the real `data/stock_data/*.xlsx` files use — shared
strings, inline values, and date-formatted serial numbers — without depending
on git-ignored data or an Excel installation.
"""

from __future__ import annotations

import csv
from pathlib import Path
import zipfile

import pytest

from abm_analysis.archive.xlsx_conversion import (
    convert_path,
    convert_workbook,
    find_workbooks,
    sanitize_filename,
)

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="rels"
    ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
</Types>
"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Target="xl/workbook.xml"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"/>
</Relationships>
"""

WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Target="worksheets/sheet1.xml"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>
  <Relationship Id="rId2" Target="worksheets/sheet2.xml"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>
</Relationships>
"""

WORKBOOK = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Daily Prices" sheetId="1" r:id="rId1"/>
    <sheet name="Notes/Meta" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>
"""

SHARED_STRINGS = """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="3" uniqueCount="3">
  <si><t>date</t></si>
  <si><t>close</t></si>
  <si><t>source</t></si>
</sst>
"""

# Style index 1 maps to numFmtId 14 (a built-in date format); index 0 is General.
STYLES = """<?xml version="1.0" encoding="UTF-8"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <cellXfs count="2">
    <xf numFmtId="0"/>
    <xf numFmtId="14" applyNumberFormat="1"/>
  </cellXfs>
</styleSheet>
"""

# Row 1 holds shared-string headers; row 2 a date serial (45000 = 2023-03-15)
# alongside a plain number; row 3 exercises an inline string and a boolean.
SHEET_ONE = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:C3"/>
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="s"><v>1</v></c>
      <c r="C1" t="s"><v>2</v></c>
    </row>
    <row r="2">
      <c r="A2" s="1"><v>45000</v></c>
      <c r="B2"><v>4109.31</v></c>
      <c r="C2" t="inlineStr"><is><t>SPX</t></is></c>
    </row>
    <row r="3">
      <c r="A3" s="1"><v>45001</v></c>
      <c r="B3"><v>4117.86</v></c>
      <c r="C3" t="b"><v>1</v></c>
    </row>
  </sheetData>
</worksheet>
"""

# Row 2 is absent entirely, so the reader must pad the gap rather than shift
# row 3 upwards — a real workbook does this wherever a row was left blank.
SHEET_TWO = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:B3"/>
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>note</t></is></c>
      <c r="B1"><v>1</v></c>
    </row>
    <row r="3">
      <c r="A3" t="inlineStr"><is><t>after gap</t></is></c>
      <c r="B3"><v>3</v></c>
    </row>
  </sheetData>
</worksheet>
"""


def write_workbook(path: Path) -> Path:
    """Write a minimal two-sheet .xlsx workbook and return its path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("xl/workbook.xml", WORKBOOK)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        archive.writestr("xl/sharedStrings.xml", SHARED_STRINGS)
        archive.writestr("xl/styles.xml", STYLES)
        archive.writestr("xl/worksheets/sheet1.xml", SHEET_ONE)
        archive.writestr("xl/worksheets/sheet2.xml", SHEET_TWO)
    return path


def read_csv_rows(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.reader(handle))


def test_convert_workbook_writes_one_csv_per_sheet(tmp_path: Path) -> None:
    workbook = write_workbook(tmp_path / "prices.xlsx")

    written = convert_workbook(workbook, tmp_path / "out")

    assert [path.name for path in written] == ["01_Daily_Prices.csv", "02_Notes_Meta.csv"]
    assert all(path.is_file() for path in written)


def test_shared_strings_inline_strings_and_booleans_are_resolved(tmp_path: Path) -> None:
    workbook = write_workbook(tmp_path / "prices.xlsx")

    written = convert_workbook(workbook, tmp_path / "out")
    rows = read_csv_rows(written[0])

    assert rows[0] == ["date", "close", "source"]
    assert rows[1][1:] == ["4109.31", "SPX"]
    assert rows[2][2] == "TRUE"


def test_date_formatted_serials_become_iso_dates(tmp_path: Path) -> None:
    """A date-styled cell must not reach the benchmark loader as a raw serial."""

    workbook = write_workbook(tmp_path / "prices.xlsx")

    rows = read_csv_rows(convert_workbook(workbook, tmp_path / "out")[0])

    assert rows[1][0] == "2023-03-15"
    assert rows[2][0] == "2023-03-16"


def test_missing_rows_are_padded_rather_than_shifted(tmp_path: Path) -> None:
    workbook = write_workbook(tmp_path / "prices.xlsx")

    rows = read_csv_rows(convert_workbook(workbook, tmp_path / "out")[1])

    assert rows[0] == ["note", "1"]
    assert rows[1] == ["", ""]
    assert rows[2] == ["after gap", "3"]


def test_convert_path_handles_a_directory_of_workbooks(tmp_path: Path) -> None:
    source = tmp_path / "stock_data"
    write_workbook(source / "spx.xlsx")
    write_workbook(source / "naq.xlsx")

    converted = convert_path(source, tmp_path / "out")

    assert {path.stem for path in converted} == {"spx", "naq"}
    # Directory input gives each workbook its own subdirectory.
    assert (tmp_path / "out" / "spx" / "01_Daily_Prices.csv").is_file()
    assert (tmp_path / "out" / "naq" / "01_Daily_Prices.csv").is_file()


def test_excel_lock_files_are_skipped(tmp_path: Path) -> None:
    """`~$` lock files appear whenever a workbook is open in Excel."""

    source = tmp_path / "stock_data"
    write_workbook(source / "spx.xlsx")
    (source / "~$spx.xlsx").write_bytes(b"not a real workbook")

    assert [path.name for path in find_workbooks(source)] == ["spx.xlsx"]


def test_a_non_workbook_reports_a_readable_error(tmp_path: Path) -> None:
    not_a_workbook = tmp_path / "broken.xlsx"
    not_a_workbook.write_bytes(b"definitely not a zip archive")

    with pytest.raises(ValueError, match="not a valid .xlsx file"):
        convert_workbook(not_a_workbook, tmp_path / "out")


def test_convert_benchmarks_subcommand_runs_end_to_end(tmp_path: Path) -> None:
    """The conversion is reachable as `abm_analysis convert-benchmarks`."""

    from abm_analysis.commands import build_parser

    workbook = write_workbook(tmp_path / "spx.xlsx")
    args = build_parser().parse_args(
        ["convert-benchmarks", str(workbook), "--output-dir", str(tmp_path / "out")]
    )

    assert args.handler(args) == 0
    assert (tmp_path / "out" / "01_Daily_Prices.csv").is_file()


def test_convert_benchmarks_subcommand_reports_a_bad_workbook(tmp_path: Path) -> None:
    from abm_analysis.commands import build_parser

    (tmp_path / "broken.xlsx").write_bytes(b"definitely not a zip archive")
    args = build_parser().parse_args(["convert-benchmarks", str(tmp_path / "broken.xlsx")])

    assert args.handler(args) == 1


def test_sheet_names_are_made_filename_safe() -> None:
    assert sanitize_filename("Notes/Meta") == "Notes_Meta"
    assert sanitize_filename("  Daily  Prices  ") == "Daily_Prices"
    assert sanitize_filename("***") == "___"
    assert sanitize_filename("") == "sheet"
