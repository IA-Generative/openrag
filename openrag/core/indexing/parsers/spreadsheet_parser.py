"""Spreadsheet ``DocumentParser``: .xlsx / .xlsm, .xls and .ods, read natively.

Converting a spreadsheet to PDF (LibreOffice) loses content: a cell is cut at
its column width when its neighbour is filled, and wide sheets split across
pages. This parser reads the cells instead and renders each sheet as a
Markdown table, which the markdown-aware chunker then splits by whole rows,
repeating the header row in every chunk (``chunk_table``).

- **One sheet = one page.** Each indexed sheet becomes a ``TextBlock`` whose
  ``page_number`` is its position, so a citation points at the sheet. The
  block opens with ``## <sheet name>``.
- **Header.** The first non-empty row of a sheet is its header; an empty
  header cell becomes the column letter.
- **Wide sheets** (more than ``columns_per_group`` columns) are split into
  column groups, each repeating the first column so a row can still be
  identified, rendered as ``## <sheet> (columns B–L)``.
- **Merged cells** take the value of their top-left cell over the whole
  range, so a grouping label or a merged header is not lost.
- **Bounded.** At most ``max_cells`` cells per file are kept; the rest is
  dropped and reported (``truncated``), never silently.
- **Reported.** ``ProcessedDocument.parse_info["spreadsheet"]`` counts sheets,
  hidden sheets (skipped unless ``include_hidden_sheets``), merged ranges,
  formulas without a cached value (rendered empty: the file was never
  recalculated) and kept / total rows. Rows are counted when they hold at
  least one value, so ``rows_kept == rows_total`` unless the file was cut.

Macros are never executed: openpyxl, xlrd and odfpy only read cell values.
.xlsx/.xlsm are streamed (``read_only``), .xls and .ods are loaded whole.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any
from xml.etree.ElementTree import iterparse

from core.utils.logging import get_logger

from ...models.document import Document, DocumentType, ProcessedDocument, TextBlock
from .document_parser import DocumentParser
from .registry import parser_registry

logger = get_logger()

DEFAULT_MAX_CELLS = 50_000
DEFAULT_COLUMNS_PER_GROUP = 12
_MAX_CELL_CHARS = 2_000
_CELL_RANGE = re.compile(r"^([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?$")


@dataclass
class _Sheet:
    name: str
    hidden: bool = False
    rows: list[list[str]] = field(default_factory=list)
    rows_total: int | None = 0
    merged_ranges: int = 0
    formulas_without_value: int = 0


@dataclass
class _Budget:
    """Cells left to keep for the whole file."""

    cells: int
    truncated: bool = False

    def take(self, width: int) -> bool:
        if self.cells - width < 0:
            self.truncated = True
            return False
        self.cells -= width
        return True


def column_letter(index: int) -> str:
    """0-based column index → Excel letters (0 → A, 26 → AA)."""
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _column_index(letters: str) -> int:
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch) - 64)
    return value - 1


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "VRAI" if value else "FAUX"
    if isinstance(value, float):
        if value != value:  # NaN, from pandas
            return ""
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, dt.datetime):
        return value.date().isoformat() if value.time() == dt.time() else value.isoformat(sep=" ")
    if isinstance(value, dt.date | dt.time):
        return value.isoformat()
    text = str(value)
    # Markdown table safety: one line, no column separator, bounded size.
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").replace("|", "\\|").strip()
    return text[:_MAX_CELL_CHARS]


class _MergeFiller:
    """Spread the top-left value of each merged range over the range."""

    def __init__(self, ranges: Iterable[tuple[int, int, int, int]]) -> None:
        # (min_row, min_col, max_row, max_col), 0-based, inclusive.
        self._ranges = [r for r in ranges if r[2] > r[0] or r[3] > r[1]]
        self._values: dict[tuple[int, int], str] = {}

    def __len__(self) -> int:
        return len(self._ranges)

    def apply(self, row_index: int, cells: list[str]) -> list[str]:
        for min_row, min_col, max_row, max_col in self._ranges:
            if not min_row <= row_index <= max_row:
                continue
            if row_index == min_row and min_col < len(cells):
                self._values[(min_row, min_col)] = cells[min_col]
            value = self._values.get((min_row, min_col), "")
            if not value:
                continue
            if len(cells) <= max_col:
                cells.extend([""] * (max_col + 1 - len(cells)))
            for col in range(min_col, max_col + 1):
                if not cells[col]:
                    cells[col] = value
        return cells


# --------------------------------------------------------------------------- #
# Readers: one per family, each yielding _Sheet objects within the budget.
# --------------------------------------------------------------------------- #


def _xlsx_merged_ranges(path: str, worksheet_path: str) -> list[tuple[int, int, int, int]]:
    """Merged ranges of one sheet, streamed from its XML part (read-only mode hides them)."""
    ranges: list[tuple[int, int, int, int]] = []
    try:
        with zipfile.ZipFile(path) as package, package.open(worksheet_path.lstrip("/")) as part:
            for _event, elem in iterparse(part, events=("end",)):
                if elem.tag.endswith("}mergeCell"):
                    match = _CELL_RANGE.match(elem.get("ref", ""))
                    if match and match.group(3):
                        c1, r1, c2, r2 = match.groups()
                        ranges.append((int(r1) - 1, _column_index(c1), int(r2) - 1, _column_index(c2)))
                elem.clear()
    except (KeyError, zipfile.BadZipFile, OSError) as exc:
        logger.debug(f"Could not read merged cells of {worksheet_path}: {exc}")
    return ranges


def _read_xlsx(path: str, budget: _Budget, include_hidden: bool) -> Iterator[_Sheet]:
    import openpyxl

    values_wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    formulas_wb = openpyxl.load_workbook(path, read_only=True, data_only=False)
    try:
        for ws, fws in zip(values_wb.worksheets, formulas_wb.worksheets, strict=True):
            sheet = _Sheet(name=ws.title, hidden=ws.sheet_state != "visible")
            if sheet.hidden and not include_hidden:
                yield sheet
                continue
            filler = _MergeFiller(_xlsx_merged_ranges(path, getattr(ws, "_worksheet_path", "")))
            sheet.merged_ranges = len(filler)
            counted = 0
            for row_index, (row, frow) in enumerate(
                zip(ws.iter_rows(values_only=True), fws.iter_rows(values_only=True), strict=False)
            ):
                cells = [_cell_text(v) for v in row]
                if any(cells):
                    counted += 1
                if budget.truncated:
                    continue
                for value, formula in zip(row, frow, strict=False):
                    if value is None and isinstance(formula, str) and formula.startswith("="):
                        sheet.formulas_without_value += 1
                cells = filler.apply(row_index, cells)
                if not any(cells):
                    continue
                if not budget.take(len(cells)):
                    continue
                sheet.rows.append(cells)
            sheet.rows_total = counted
            yield sheet
    finally:
        values_wb.close()
        formulas_wb.close()


def _read_xls(path: str, budget: _Budget, include_hidden: bool) -> Iterator[_Sheet]:
    import xlrd

    book = xlrd.open_workbook(path, formatting_info=True, on_demand=True)
    try:
        for sheet_index in range(book.nsheets):
            xs = book.sheet_by_index(sheet_index)
            sheet = _Sheet(name=xs.name, hidden=xs.visibility != 0)
            if sheet.hidden and not include_hidden:
                yield sheet
                continue
            filler = _MergeFiller((rlo, clo, rhi - 1, chi - 1) for rlo, rhi, clo, chi in xs.merged_cells)
            sheet.merged_ranges = len(filler)
            counted = 0
            for row_index in range(xs.nrows):
                cells = []
                for cell in xs.row(row_index):
                    value = cell.value
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        try:
                            value = xlrd.xldate_as_datetime(value, book.datemode)
                        except (ValueError, OverflowError):
                            pass
                    elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                        value = bool(value)
                    elif cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
                        value = None
                    cells.append(_cell_text(value))
                cells = filler.apply(row_index, cells)
                if not any(cells):
                    continue
                counted += 1
                if not budget.truncated and budget.take(len(cells)):
                    sheet.rows.append(cells)
            sheet.rows_total = counted
            book.unload_sheet(sheet_index)
            yield sheet
    finally:
        book.release_resources()


def _ods_hidden_sheets(path: str) -> set[str]:
    """Names of the sheets an .ods hides.

    Visibility is not on the table itself: the table names a style whose
    ``style:table-properties`` carries ``table:display="false"``. pandas does
    not expose it, so it is read with odfpy directly.
    """
    from odf.opendocument import load
    from odf.style import Style, TableProperties
    from odf.table import Table

    doc = load(path)
    hidden_styles = set()
    for container in (doc.automaticstyles, doc.styles):
        for style in container.getElementsByType(Style):
            if style.getAttribute("family") != "table":
                continue
            if any(tp.getAttribute("display") == "false" for tp in style.getElementsByType(TableProperties)):
                hidden_styles.add(style.getAttribute("name"))
    return {
        str(table.getAttribute("name"))
        for table in doc.spreadsheet.getElementsByType(Table)
        if table.getAttribute("stylename") in hidden_styles
    }


def _read_ods(path: str, budget: _Budget, include_hidden: bool) -> Iterator[_Sheet]:
    # pandas' odf reader expands repeated rows/columns and spans; merged ranges
    # are not exposed through it, so they are not reported.
    import pandas as pd

    hidden = _ods_hidden_sheets(path)
    frames = pd.read_excel(path, sheet_name=None, header=None, engine="odf", dtype=object)
    for name, frame in frames.items():
        sheet = _Sheet(name=str(name), hidden=str(name) in hidden)
        if sheet.hidden and not include_hidden:
            yield sheet
            continue
        counted = 0
        for values in frame.itertuples(index=False, name=None):
            cells = [_cell_text(v) for v in values]
            if not any(cells):
                continue
            counted += 1
            if not budget.truncated and budget.take(len(cells)):
                sheet.rows.append(cells)
        sheet.rows_total = counted
        yield sheet


_READERS = {"xlsx": _read_xlsx, "xlsm": _read_xlsx, "xls": _read_xls, "ods": _read_ods}


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def _markdown_table(rows: list[list[str]]) -> str:
    header, body = rows[0], rows[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["---"] * len(header)) + "|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def render_sheet(sheet: _Sheet, columns_per_group: int) -> str:
    """Markdown for one sheet: heading + one table, or one table per column group."""
    if not sheet.rows:
        return ""
    width = max(max((i + 1 for i, c in enumerate(row) if c), default=0) for row in sheet.rows)
    if width == 0:
        return ""
    rows = [(row + [""] * width)[:width] for row in sheet.rows]
    header = [cell or column_letter(i) for i, cell in enumerate(rows[0])]
    rows[0] = header
    if width <= columns_per_group:
        return f"## {sheet.name}\n\n{_markdown_table(rows)}"
    # Column groups, each repeating the first column so a row stays identifiable.
    step = max(1, columns_per_group - 1)
    parts = []
    for start in range(1, width, step):
        cols = [0, *range(start, min(start + step, width))]
        label = f"{column_letter(cols[1])}–{column_letter(cols[-1])}"
        table = _markdown_table([[row[c] for c in cols] for row in rows])
        parts.append(f"## {sheet.name} (colonnes {label})\n\n{table}")
    return "\n\n".join(parts)


@parser_registry.register("spreadsheet")
class SpreadsheetParser(DocumentParser):
    """Read .xlsx/.xlsm/.xls/.ods cells and render each sheet as Markdown tables."""

    def __init__(
        self,
        *,
        max_cells: int = DEFAULT_MAX_CELLS,
        columns_per_group: int = DEFAULT_COLUMNS_PER_GROUP,
        include_hidden_sheets: bool = False,
    ) -> None:
        self._max_cells = max(1, max_cells)
        self._columns_per_group = max(2, columns_per_group)
        self._include_hidden = include_hidden_sheets

    def supported_types(self) -> list[str]:
        return [DocumentType.SPREADSHEET.value]

    async def parse(self, document: Document) -> ProcessedDocument:
        if not document.raw_bytes and not document.source_path:
            return ProcessedDocument(document_id=document.id, metadata=dict(document.metadata))
        ext = Document.type_extension(document.filename, document.metadata.get("mimetype"))
        reader = _READERS.get(ext)
        if reader is None:
            raise ValueError(f"Unsupported spreadsheet extension {ext!r}; expected one of {sorted(_READERS)}")
        async with document.as_temporary_file(suffix=f".{ext}") as path:
            blocks, info = await asyncio.to_thread(self._extract, reader, str(path))
        if info["truncated"]:
            logger.bind(filename=document.filename).warning(
                f"Spreadsheet truncated at {self._max_cells} cells: kept {info['rows_kept']} of "
                f"{info['rows_total']} rows"
            )
        return ProcessedDocument(
            document_id=document.id,
            text_blocks=blocks,
            metadata=dict(document.metadata),
            page_count=len(blocks),
            parse_info={"spreadsheet": info},
        )

    def _extract(self, reader, path: str) -> tuple[list[TextBlock], dict[str, Any]]:
        budget = _Budget(self._max_cells)
        blocks: list[TextBlock] = []
        sheets = hidden = merged = formulas = rows_kept = 0
        rows_total: int | None = 0
        for sheet in reader(path, budget, self._include_hidden):
            sheets += 1
            if sheet.hidden:
                hidden += 1
                if not self._include_hidden:
                    continue
            merged += sheet.merged_ranges
            formulas += sheet.formulas_without_value
            rows_kept += len(sheet.rows)
            rows_total = None if rows_total is None or sheet.rows_total is None else rows_total + sheet.rows_total
            text = render_sheet(sheet, self._columns_per_group)
            if text:
                blocks.append(TextBlock(text=text, page_number=len(blocks) + 1))
        info = {
            "sheets": sheets,
            "sheets_indexed": len(blocks),
            "hidden_sheets": hidden,
            "hidden_sheets_skipped": 0 if self._include_hidden else hidden,
            "merged_ranges": merged,
            "formulas_without_value": formulas,
            "rows_kept": rows_kept,
            "rows_total": rows_total,
            "truncated": budget.truncated,
            "max_cells": self._max_cells,
        }
        return blocks, info
