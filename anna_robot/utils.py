"""Small shared utilities."""

from __future__ import annotations

import re


def clean_text(text: str) -> str:
    """Strip markdown emphasis and non-ASCII characters so the TTS engine
    doesn't choke on emoji / accented characters returned by the LLM."""
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"[^\x00-\x7F]", "", text)
    return text.replace("\n", " ").strip()
