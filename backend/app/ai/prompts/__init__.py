"""Versioned prompt files (spec 14). The file name without `.md` is the prompt version."""

from pathlib import Path

PROMPT_DIR = Path(__file__).parent

RECEIPT_EXTRACT = "receipt_extract.v1"
CATEGORY_CLASSIFY = "category_classify.v1"
BANK_ROWS = "bank_rows.v1"
COMPARISON_COMMENTARY = "comparison_commentary.v1"
ASSISTANT = "assistant.v1"


def load_prompt(version: str) -> str:
    return (PROMPT_DIR / f"{version}.md").read_text(encoding="utf-8")


def load_bank_prompt(bank_key: str | None) -> str:
    """The bank row prompt, plus the hints of one supported bank (`prompts/banks/<bank>.md`).
    A bank without a hints file (or no bank at all) gets the general prompt only."""
    prompt = load_prompt(BANK_ROWS)
    if bank_key and bank_key.isalnum():
        hints = PROMPT_DIR / "banks" / f"{bank_key.lower()}.md"
        if hints.is_file():
            prompt += "\n\n" + hints.read_text(encoding="utf-8")
    return prompt
