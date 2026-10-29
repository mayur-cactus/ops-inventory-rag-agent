import logging
from pathlib import Path
from typing import IO, List, Optional, Union

import pdfplumber
from agno.knowledge.document.base import Document
from agno.knowledge.reader.pdf_reader import PDFReader

# pdfplumber logs a warning per page for fonts without a bounding box.
logging.getLogger("pdfminer").setLevel(logging.ERROR)

# The inventory tables have 12 raw columns, but a word can straddle a column
# boundary. These groups of raw columns are cropped and read as one region.
INVENTORY_COLS = 12
INVENTORY_GROUPS = [
    ("Service", (1, 2)),
    ("Webpages", (3, 3)),
    ("OS", (4, 4)),
    ("Technology", (5, 5)),
    ("Framework", (6, 6)),
    ("DB", (7, 7)),
    ("Status", (8, 8)),
    ("Comments", (9, 10)),
]


def _clean(text: Optional[str]) -> str:
    return " ".join((text or "").split())


def _group_text(page, cells, first: int, last: int) -> str:
    boxes = [c for c in cells[first : last + 1] if c is not None]
    if not boxes:
        return ""
    x0 = max(min(b[0] for b in boxes), 0)
    top = max(min(b[1] for b in boxes), 0)
    x1 = min(max(b[2] for b in boxes), page.width)
    bottom = min(max(b[3] for b in boxes), page.height)
    if x1 <= x0 or bottom <= top:
        return ""
    return _clean(page.crop((x0, top, x1, bottom)).extract_text())


class TableAwareReader(PDFReader):
    """PDFReader that keeps inventory-table rows together, one chunk per row."""

    _used_generic = False

    def read(
        self,
        pdf: Union[str, Path, IO, None] = None,
        name: Optional[str] = None,
        password: Optional[str] = None,
    ) -> List[Document]:
        doc_name = name or (Path(pdf).name if isinstance(pdf, (str, Path)) else "pdf")
        documents: List[Document] = []
        text_pages: List[Document] = []

        with pdfplumber.open(pdf, password=password) as handle:
            for number, page in enumerate(handle.pages, start=1):
                self._used_generic = False
                rows = self._inventory_rows(page)
                for index, content in enumerate(rows):
                    documents.append(
                        Document(
                            name=doc_name,
                            id=f"{doc_name}_{number}_row{index}",
                            meta_data={"page": number},
                            content=content,
                        )
                    )
                if rows and not self._used_generic:
                    continue  # fully structured page; no need for flat text
                text = _clean(page.extract_text())
                if text:
                    text_pages.append(
                        Document(
                            name=doc_name,
                            id=f"{doc_name}_{number}",
                            meta_data={"page": number},
                            content=text,
                        )
                    )

        if text_pages and self.chunk:
            text_pages = [c for page_doc in text_pages for c in self.chunk_document(page_doc)]
        return documents + text_pages

    def _generic_rows(self, page, table) -> List[str]:
        """One chunk per row for tables whose layout is not the 12-column one."""
        rows: List[str] = []
        for row in table.rows:
            cells = [c for c in row.cells if c is not None]
            if not cells:
                continue
            # The name column is split in two raw cells, so read both as one
            # region; every other cell is read on its own, which keeps each
            # value next to its column.
            parts = [_group_text(page, cells, 0, min(1, len(cells) - 1))]
            parts += [_group_text(page, [c], 0, 0) for c in cells[2:]]
            text = " | ".join(p for p in parts if p)
            if len(text) >= 15:
                rows.append(text)
        return rows

    def _inventory_rows(self, page) -> List[str]:
        rows: List[str] = []
        for table in page.find_tables():
            cols = max((len(r.cells) for r in table.rows), default=0)
            if cols >= 5 and len(table.rows) >= 2 and cols != INVENTORY_COLS:
                rows.extend(self._generic_rows(page, table))
                self._used_generic = True
                continue
            if cols != INVENTORY_COLS:
                continue
            section = ""
            for row in table.rows:
                values = {
                    label: _group_text(page, row.cells, first, last)
                    for label, (first, last) in INVENTORY_GROUPS
                }
                filled = {k: v for k, v in values.items() if v}
                if not filled:
                    continue
                # A row with only the service column filled is a section heading.
                if list(filled) == ["Service"] and len(filled["Service"]) > 3:
                    section = filled["Service"]
                    continue
                if "Service" not in filled or len(filled) < 3:
                    continue
                if filled["Service"].startswith("Entity"):
                    continue  # header row
                compact = filled["Service"].replace(" ", "")
                if compact != filled["Service"]:
                    filled["Service"] = f"{filled['Service']} ({compact})"
                prefix = f"Section: {section} | " if section else ""
                rows.append(
                    prefix + " | ".join(f"{k}: {v}" for k, v in filled.items())
                )
        return rows
