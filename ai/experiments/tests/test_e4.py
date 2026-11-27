"""E4: the synthetic personal data is valid (checksums), the generator is reproducible and covers
every type, OCR noise changes the value, and the scoring counts the right things."""

import random

from rbx_eval import e4


def test_generated_identifiers_pass_their_checksums() -> None:
    f = e4.Faker(1)
    for _ in range(200):
        assert e4.luhn_valid(f.card().replace(" ", "").replace("-", ""))
        assert e4.tckn_valid(f.tckn())
        assert not e4.tckn_valid(f.tckn(valid=False))
        assert e4.iban_valid(f.iban())
        assert not e4.luhn_valid(f.luhn_invalid16())
        ean = f.ean13()
        assert len(ean) == 13 and e4.ean13_check(ean[:12]) == ean[-1]


def test_known_values() -> None:
    assert e4.luhn_valid("4111111111111111")  # a public test card number
    assert e4.tckn_valid("10000000146")  # a public test TCKN
    assert e4.iban_valid("TR33 0006 1005 1978 6457 8413 26")  # the classic example IBAN


def test_the_generator_is_reproducible_and_covers_every_type() -> None:
    first = e4.generate(600, seed=5)
    second = e4.generate(600, seed=5)

    assert [s.text for s in first] == [s.text for s in second]
    assert len(first) == 600
    types = {span.type for s in first for span in s.spans}
    assert types == set(e4.TYPE_LABELS)
    assert sum(s.bank for s in first) == 150
    assert any(span.noisy for s in first for span in s.spans)


def test_names_in_one_text_share_no_part() -> None:
    for sample in e4.generate(300, seed=3):
        parts = [p for span in sample.spans for p in span.names]
        assert len(parts) == len(set(parts))


def test_ocr_noise_always_changes_the_value() -> None:
    r = random.Random(0)
    for value in ("TR33 0006 1005 1978 6457 8413 26", "4543-6012-3456-7890", "10000000146"):
        for _ in range(20):
            assert e4.ocr_noise(value, r) != value


def test_scoring() -> None:
    sample = e4.Sample(
        "x",
        "Sayın Ayşe Yılmaz\nIBAN: TR33 0006 1005 1978 6457 8413 26\nTOPLAM *12,50\nVKN: 1234567890",
        False,
        [
            e4.Span("name_keyword", "Ayşe Yılmaz", True, ["Ayşe", "Yılmaz"]),
            e4.Span("iban", "TR33 0006 1005 1978 6457 8413 26", True),
            e4.Span("total", "12,50", False),
            e4.Span("tax_number", "1234567890", False),
        ],
    )
    masked = {"x": "Sayın [NAME]\nIBAN: [IBAN]\nTOPLAM *12,50\nVKN: [TCKN]"}

    result = e4.score([sample], masked)

    by_type = {row["type"]: row for row in result["per_type"]}
    assert by_type["name_keyword"]["removed"] == 1
    assert by_type["iban"]["removed"] == 1
    assert by_type["total"]["removed"] == 0
    assert by_type["tax_number"]["removed"] == 1  # a false positive
    assert result["recall_all"]["value"] == 1.0
    assert result["false_positive_rate"]["value"] == 0.5
