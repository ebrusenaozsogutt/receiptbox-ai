"""E3: the question set is valid, and the scoring counts tools, numbers, names, dates, "no data"
and hallucinations the way the report describes."""

from datetime import date

from rbx_eval import EXPERIMENTS_DIR, e3

import yaml

from app.ai.answer_check import allowed_numbers

BENCH = yaml.safe_load((EXPERIMENTS_DIR / "assistant_benchmark.yaml").read_text("utf-8"))
KNOWN_KINDS = set(e3.DEFAULT_TOOLS) | {"no_data"}


def test_the_question_set() -> None:
    questions = BENCH["questions"]
    ids = [q["id"] for q in questions]
    assert 60 <= len(questions) <= 100
    assert len(ids) == len(set(ids))
    assert BENCH["today"] == date(2026, 11, 26)
    for q in questions:
        assert q["gold"]["kind"] in KNOWN_KINDS, q["id"]
        assert e3.expected_tools(q) is not None
        if q["gold"]["kind"] == "no_data":
            assert q.get("tools"), f"{q['id']}: a no-data question names the tools to expect"
    groups = {q["group"] for q in questions}
    assert {"comparison", "no_data", "merchant", "relative_period", "out_of_scope"} <= groups
    assert any("geçen yıl" in q["question"].lower() for q in questions)


def score(question: dict, gold: dict, answer: str, tools: list[str], **kw) -> dict:
    allowed = allowed_numbers([kw.pop("outputs", ""), question.get("question", "")])
    return e3.score(
        question,
        gold,
        answer=answer,
        tools_called=tools,
        allowed_numbers=allowed,
        corrections=kw.get("corrections", 0),
        outcome=kw.get("outcome", "ANSWERED"),
        provider_error=kw.get("provider_error", False),
    )


SPEND = {"question": "Bu ay markete ne kadar?", "gold": {"kind": "spend"}}


def test_a_correct_amount() -> None:
    result = score(
        SPEND,
        {"numbers": ["9.891,95"]},
        "Bu ay markete 9.891,95 TL harcadın.",
        ["aggregate_spending"],
        outputs="9.891,95 TL",
    )
    assert result["tool_ok"] and result["numbers_ok"] and result["correct"]
    assert not result["first_answer_hallucinated"]
    assert result["final_unsupported_numbers"] == []


def test_a_wrong_amount_and_a_wrong_tool() -> None:
    result = score(SPEND, {"numbers": ["9.891,95"]}, "Markete 9.800 TL.", ["search_products"])
    assert not result["tool_ok"]
    assert not result["numbers_ok"] and not result["correct"]
    assert result["final_unsupported_numbers"] == ["9.800"]


def test_a_corrected_or_templated_turn_counts_as_a_first_answer_hallucination() -> None:
    gold = {"numbers": ["1.000,00"]}
    assert score(SPEND, gold, "1.000,00 TL", ["aggregate_spending"], corrections=1)[
        "first_answer_hallucinated"
    ]
    assert score(SPEND, gold, "1.000,00 TL", ["aggregate_spending"], outcome="TEMPLATE")[
        "first_answer_hallucinated"
    ]
    # A template after a provider failure is not the model's hallucination.
    assert not score(
        SPEND, gold, "1.000,00 TL", ["aggregate_spending"], outcome="TEMPLATE", provider_error=True
    )["first_answer_hallucinated"]


def test_names_and_dates() -> None:
    question = {"question": "Garantisi bitecek ürünler?", "gold": {"kind": "warranty_ending"}}
    gold = {"names": ["AirPods Pro"], "dates": [date(2026, 12, 16)]}
    good = score(
        question,
        gold,
        "AirPods Pro'nun garantisi 16 Aralık 2026'da bitiyor.",
        ["get_upcoming_deadlines"],
        outputs="2026-12-16",
    )
    wrong_date = score(question, gold, "AirPods Pro: 17 Aralık 2026", ["get_upcoming_deadlines"])
    assert good["correct"] and good["dates_ok"] and good["names_ok"]
    assert not wrong_date["correct"]


def test_no_data_answers() -> None:
    question = {"question": "Amazon'a ne kadar ödedim?", "tools": ["aggregate_spending"],
                "gold": {"kind": "no_data"}}  # fmt: skip
    gold = {"no_data": True}
    assert score(question, gold, "Kayıtlarında bununla ilgili bilgi bulamadım.",
                 ["aggregate_spending"])["correct"]  # fmt: skip
    assert score(question, gold, "Bu dönemde kayıtlı bir harcaman yok.", ["aggregate_spending"])[
        "correct"
    ]
    assert score(question, gold, "Bu dönemde 0,00 TL harcadın.", ["aggregate_spending"],
                 outputs="0,00 TL")["correct"]  # fmt: skip
    assert not score(question, gold, "Amazon'a 120 TL ödedin.", ["aggregate_spending"])["correct"]


def test_out_of_scope_wants_no_tool_and_no_number() -> None:
    question = {"question": "Dolar bugün kaç TL?", "gold": {"kind": "out_of_scope"}}
    gold = {"out_of_scope": True}
    good = score(question, gold, "Yalnızca alışveriş kayıtların hakkında yardımcı olabilirim.", [])
    bad = score(question, gold, "Dolar 34,50 TL.", [])
    assert good["tool_ok"] and good["correct"]
    assert not bad["correct"]
    assert not score(question, gold, "Bilmiyorum.", ["query_transactions"])["tool_ok"]
