"""Versioned prompt files (spec 14). The file name without `.md` is the prompt version."""

from pathlib import Path

PROMPT_DIR = Path(__file__).parent

RECEIPT_EXTRACT = "receipt_extract.v1"


def load_prompt(version: str) -> str:
    return (PROMPT_DIR / f"{version}.md").read_text(encoding="utf-8")
