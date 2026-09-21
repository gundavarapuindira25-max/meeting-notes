"""
Turns an uploaded transcript file into plain text the summarizer can use.

Supports:
- .txt — used as-is
- .vtt (WebVTT, e.g. exported from Zoom/Google Meet/Otter) — strips the
  WEBVTT header, cue numbers, and timestamp lines, keeping only spoken text
"""

import re

_TIMESTAMP_LINE = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}")
_CUE_NUMBER_LINE = re.compile(r"^\d+$")


def parse_vtt(content: str) -> str:
    lines = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "WEBVTT" or line.startswith("NOTE"):
            continue
        if _TIMESTAMP_LINE.match(line):
            continue
        if _CUE_NUMBER_LINE.match(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def extract_text(filename: str, content: str) -> str:
    """Dispatches on file extension; falls back to raw content for .txt or
    anything unrecognized (e.g. pasted text with no filename)."""
    if filename and filename.lower().endswith(".vtt"):
        return parse_vtt(content)
    return content
