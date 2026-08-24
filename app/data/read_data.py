"""
read_data.py

Reads video content data from content.csv and returns the first row
that hasn't been processed yet (status == "not").

Also provides update_row_status() to write per-platform upload results
(success/fail + error message) back into content.csv, and to mark the
row as "done" once processing has finished.
"""

import csv
import os
from typing import Optional, TypedDict

CSV_PATH = os.path.join(os.path.dirname(__file__), "content.csv")

# Columns written back to content.csv describing the outcome of each
# platform's upload attempt for a given row.
FIELDNAMES = [
    "title",
    "description",
    "hashtags",
    "status",
    "yt_status",
    "yt_error",
    "insta_status",
    "insta_error",
    "fb_status",
    "fb_error",
]


class ContentRow(TypedDict):
    id: int
    title: str
    description: str
    hashtags: list[str]
    status: str


def _read_rows(csv_path: str = CSV_PATH) -> tuple[list[str], list[dict]]:
    """Reads content.csv and returns (fieldnames, rows).

    content.csv sometimes contains bytes that aren't valid in any single
    encoding (e.g. emoji mangled by a copy/paste through different tools,
    or Excel saving as Windows-1252). Try clean decodes first, and if
    those fail, fall back to UTF-8 with invalid bytes replaced by U+FFFD
    rather than crashing the whole run.
    """
    encodings_to_try = ["utf-8-sig", "cp1252"]

    for encoding in encodings_to_try:
        try:
            with open(csv_path, newline="", encoding=encoding) as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or FIELDNAMES
                rows = list(reader)
            return fieldnames, rows
        except UnicodeDecodeError:
            continue

    with open(csv_path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or FIELDNAMES
        rows = list(reader)
    return fieldnames, rows


def read_data(csv_path: str = CSV_PATH) -> Optional[ContentRow]:
    """
    Read content.csv and return the first row whose status is "not"
    (i.e. not yet processed/uploaded).

    Row ids are 1-based and match the row's position in the file, so they
    line up with asset filenames like images/1.png and videos/1.mp4.

    Returns None if the file doesn't exist or every row is already "done".
    """
    if not os.path.exists(csv_path):
        return None

    _, rows = _read_rows(csv_path)

    for row_id, row in enumerate(rows, start=1):
        # Skip blank/trailing lines in the csv
        if not row or not any((value or "").strip() for value in row.values()):
            continue

        status = (row.get("status") or "").strip().lower()
        if status != "not":
            continue

        hashtags_raw = (row.get("hashtags") or "").strip()
        hashtags = [tag for tag in hashtags_raw.split() if tag]

        return {
            "id": row_id,
            "title": (row.get("title") or "").strip(),
            "description": (row.get("description") or "").strip(),
            "hashtags": hashtags,
            "status": status,
        }

    return None


def read_row_by_id(row_id: int, csv_path: str = CSV_PATH) -> Optional[ContentRow]:
    """
    Read content.csv and return the row at the given 1-based row_id,
    regardless of its "status" column (unlike read_data(), which only
    returns unprocessed rows).

    Row ids are 1-based and match the row's position in the file, so they
    line up with asset filenames like images/1.png and videos/1.mp4.

    Returns None if the file doesn't exist or row_id is out of range.
    """
    if not os.path.exists(csv_path):
        return None

    _, rows = _read_rows(csv_path)

    index = row_id - 1
    if index < 0 or index >= len(rows):
        return None

    row = rows[index]
    if not row or not any((value or "").strip() for value in row.values()):
        return None

    hashtags_raw = (row.get("hashtags") or "").strip()
    hashtags = [tag for tag in hashtags_raw.split() if tag]

    return {
        "id": row_id,
        "title": (row.get("title") or "").strip(),
        "description": (row.get("description") or "").strip(),
        "hashtags": hashtags,
        "status": (row.get("status") or "").strip().lower(),
    }


def update_row_status(
    row_id: int,
    *,
    yt_status: Optional[str] = None,
    yt_error: str = "",
    insta_status: Optional[str] = None,
    insta_error: str = "",
    fb_status: Optional[str] = None,
    fb_error: str = "",
    mark_done: bool = True,
    csv_path: str = CSV_PATH,
) -> None:
    """
    Writes per-platform upload results back into content.csv for the row
    with the given 1-based row_id (matching the id returned by read_data()).

    yt_status / insta_status / fb_status should be "success" or "failed"
    (pass None to leave a platform's columns untouched, e.g. if it was
    skipped because you weren't logged in). yt_error / insta_error /
    fb_error hold the error message when the corresponding status is
    "failed", otherwise they're left blank.

    If mark_done is True (default), the row's overall "status" column is
    set to "done" so read_data() won't pick it up again on the next run.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(csv_path)

    fieldnames, rows = _read_rows(csv_path)

    # Make sure the new tracking columns are always present in the header,
    # even for CSVs written before this feature existed.
    for col in FIELDNAMES:
        if col not in fieldnames:
            fieldnames.append(col)

    index = row_id - 1
    if index < 0 or index >= len(rows):
        raise IndexError(f"No row with id {row_id} in {csv_path}")

    row = rows[index]

    if yt_status is not None:
        row["yt_status"] = yt_status
        row["yt_error"] = yt_error if yt_status == "failed" else ""
    if insta_status is not None:
        row["insta_status"] = insta_status
        row["insta_error"] = insta_error if insta_status == "failed" else ""
    if fb_status is not None:
        row["fb_status"] = fb_status
        row["fb_error"] = fb_error if fb_status == "failed" else ""

    if mark_done:
        row["status"] = "done"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})
