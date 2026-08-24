"""
read_data.py

Reads video content data from content.csv and returns the first row
that hasn't been processed yet (status == "not").
"""

import csv
import os
from typing import Optional, TypedDict

CSV_PATH = os.path.join(os.path.dirname(__file__), "content.csv")


class ContentRow(TypedDict):
    id: int
    title: str
    description: str
    hashtags: list[str]
    status: str


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

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row_id, row in enumerate(reader, start=1):
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
