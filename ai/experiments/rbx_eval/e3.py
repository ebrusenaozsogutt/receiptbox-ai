"""E3 scoring (spec 19): tool-selection accuracy, answer / numeric correctness, hallucination
rate, correct "no data" answers, latency. Pure functions (unit-tested in tests/test_e3.py).

- Tool selection: at least one of the expected tools was called (out-of-scope questions: none).
- Numeric correctness: every gold number appears in the answer (Turkish canonical form, so
  "8.999,00" = "8.999"); names and dates of the gold answer must appear too.
- "No data": the answer says nothing was found and uses no number that no tool returned.
- Hallucination (first answer): the model's first answer used a number that was in no tool output
  of the turn, i.e. the post-check had to correct it or replace it with the template. The final
  answer is checked again (it should never have one: the app guarantees that).
"""

import re
from datetime import date
from typing import Any

from app.ai.answer_check import canonical, numbers_in
from app.ai.tools.base import MONTHS_TR
from app.core.text import normalize_alias_key

DEFAULT_TOOLS: dict[str, list[str]] = {
    "spend": ["aggregate_spending", "query_transactions"],
    "compare": ["compare_periods", "aggregate_spending"],
    "top": ["query_transactions"],
    "biggest": ["query_transactions"],
    "count": ["query_transactions"],
    "warranty_ending": ["get_upcoming_deadlines", "search_products"],
    "return_ending": ["get_upcoming_deadlines", "search_products"],
    "warranty_end": ["get_product_details", "search_products", "get_upcoming_deadlines"],
    "product_price": ["search_products", "get_product_details", "query_transactions"],
    "documents": ["find_documents"],
    "products": ["search_products"],
    "remaining_installments": ["get_installment_schedule"],
    "month_due": ["get_installment_schedule"],
    "last_installment": ["get_installment_schedule", "get_upcoming_deadlines"],
    "out_of_scope": [],
}

# "Kayıtlarında bununla ilgili bilgi bulamadım.", "... kayıtlı bir harcaman yok.", "bulunmuyor".
_NO_DATA = re.compile(r"BULAMAD|BULUNAMAD|BULUNMUYOR|GORUNMUYOR|GÖRÜNMÜYOR|\bYOK\b")


def norm(text: str) -> str:
    return normalize_alias_key(text)


def expected_tools(question: dict[str, Any]) -> list[str]:
    if "tools" in question:
        return list(question["tools"])
    return DEFAULT_TOOLS[question["gold"]["kind"]]


def date_mentioned(day: date, answer: str) -> bool:
    text = norm(answer)
    spoken = norm(f"{day.day} {MONTHS_TR[day.month - 1]}")
    return spoken in text or day.strftime("%d.%m.%Y") in answer or day.isoformat() in answer


def score(
    question: dict[str, Any],
    gold: dict[str, Any],
    *,
    answer: str,
    tools_called: list[str],
    allowed_numbers: set[str],
    corrections: int,
    outcome: str,
    provider_error: bool,
) -> dict[str, Any]:
    expected = expected_tools(question)
    tool_ok = (not tools_called) if not expected else any(t in tools_called for t in expected)
    answer_numbers = {canonical(n) for n in numbers_in(answer)}
    unsupported = [n for n in numbers_in(answer) if canonical(n) not in allowed_numbers]
    result: dict[str, Any] = {
        "tool_ok": tool_ok,
        "first_answer_hallucinated": corrections > 0
        or (outcome == "TEMPLATE" and not provider_error),
        "final_unsupported_numbers": unsupported,
        "numbers_ok": None,
        "names_ok": None,
        "dates_ok": None,
    }
    if gold.get("out_of_scope"):
        result["correct"] = not tools_called and not answer_numbers
        result["kind"] = "out_of_scope"
        return result
    if gold.get("no_data"):
        # "bulamadım" / "harcaman yok", or saying the amount is zero ("0,00 TL harcadın").
        says_none = bool(_NO_DATA.search(norm(answer))) or answer_numbers == {"0"}
        result["correct"] = says_none and not unsupported
        result["kind"] = "no_data"
        return result
    numbers_ok = all(canonical(n) in answer_numbers for n in gold.get("numbers", []))
    names_ok = all(norm(name) in norm(answer) for name in gold.get("names", []))
    dates_ok = all(date_mentioned(d, answer) for d in gold.get("dates", []))
    result.update(
        {
            "kind": "data",
            "numbers_ok": numbers_ok if gold.get("numbers") else None,
            "names_ok": names_ok if gold.get("names") else None,
            "dates_ok": dates_ok if gold.get("dates") else None,
            "correct": numbers_ok and names_ok and dates_ok,
        }
    )
    return result
