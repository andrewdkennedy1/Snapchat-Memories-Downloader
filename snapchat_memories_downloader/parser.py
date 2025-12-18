from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Callable


DOWNLOAD_URL_RE = re.compile(
    r"""downloadMemories\(\s*(['"])([^'"]+)\1""",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC")


class MemoriesParser(HTMLParser):
    """
    Parse Snapchat memories_history.html to extract memory data.

    Snapchat's HTML format:
    - Table rows (<tr>) contain memory entries
    - Each row has cells (<td>) with: date, media type, location
    - Download link is in <a onclick="downloadMemories('URL', ...)">
    """

    def __init__(self):
        super().__init__()
        self.memories: list[dict] = []
        self.current_row: dict = {}
        self.current_tag: str | None = None
        self.in_table_row = False
        self.cell_index = 0

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_table_row = True
            self.current_row = {}
            self.cell_index = 0
        elif tag == "td" and self.in_table_row:
            self.current_tag = "td"
            self.cell_index += 1
        elif tag == "a" and self.in_table_row:
            for attr_name, attr_value in attrs:
                if (
                    attr_name == "onclick"
                    and attr_value
                    and "downloadMemories" in attr_value
                ):
                    match = DOWNLOAD_URL_RE.search(attr_value)
                    if match:
                        self.current_row["url"] = match.group(2)

    def handle_data(self, data):
        if self.current_tag != "td" or not self.in_table_row:
            return

        data = data.strip()
        if not data:
            return

        if DATE_RE.fullmatch(data):
                self.current_row["date"] = data
        elif data in ["Image", "Video"]:
            self.current_row["media_type"] = data
        elif "Latitude, Longitude:" in data:
            coords = data.replace("Latitude, Longitude:", "").strip()
            lat_lon = coords.split(",")
            if len(lat_lon) == 2:
                self.current_row["latitude"] = lat_lon[0].strip()
                self.current_row["longitude"] = lat_lon[1].strip()

    def handle_endtag(self, tag):
        if tag == "td":
            self.current_tag = None
        elif tag == "tr" and self.in_table_row:
            if "url" in self.current_row and "date" in self.current_row:
                self.memories.append(self.current_row.copy())
            self.in_table_row = False
            self.current_row = {}


def parse_html_file(html_path: str, log: Callable[[str], None] | None = print) -> list:
    if log:
        log(f"Parsing {html_path}...")
    parser = MemoriesParser()
    with open(html_path, "r", encoding="utf-8", errors="replace") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            parser.feed(chunk)

    if log:
        log(f"Found {len(parser.memories)} memories")
    return parser.memories
