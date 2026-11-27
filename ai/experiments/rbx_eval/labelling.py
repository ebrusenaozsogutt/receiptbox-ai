"""The E1 labelling logic (label_receipts.py is the terminal around it; tested in
tests/test_labelling.py).

Every field starts pre-filled from what the app saved and is marked "unverified". Only what the
owner confirms (Enter) or corrects becomes gold ("verified": true); "?" leaves a field
unverified (it does not count), "-" says the receipt has no such field (verified empty).
"""

import json
from collections.abc import Callable
from typing import Any

from rbx_eval.e1 import Receipt, to_iso_date, to_minor

from app.models.enums import CategoryKey

FIELD_PROMPTS = {
    "merchant": "İşletme adı (fişte yazdığı gibi)",
    "date": "Tarih (GG.AA.YYYY)",
    "total_minor": "Toplam tutar (ör. 270,30)",
    "category": "Kategori (" + ", ".join(k.value for k in CategoryKey) + ")",
}
HELP = (
    "Enter = doğru, yeni değer = düzelt, - = fişte yok, ? = şimdilik geç (doğrulanmaz), "
    "q = kaydet ve çık"
)


class Quit(Exception):
    """The owner typed q: save what is done and stop."""


def show_value(field: str, value: Any) -> str:
    if value is None:
        return "(boş)"
    if field == "total_minor":
        lira, kurus = divmod(int(value), 100)
        return f"{lira:,}".replace(",", ".") + f",{kurus:02d}"
    if field == "date":
        y, m, d = str(value).split("-")
        return f"{d}.{m}.{y}"
    return str(value)


def parse_field(field: str, text: str) -> Any:
    """The owner's typed value -> the stored value; ValueError when it cannot be read."""
    text = text.strip()
    if field == "date":
        value = to_iso_date(text)
    elif field == "total_minor":
        value = to_minor(text)
    elif field == "category":
        value = CategoryKey(text.upper()).value
    else:
        value = text or None
    if value is None:
        raise ValueError(field)
    return value


def answer_field(field: str, prefill: Any, answer: str) -> dict[str, Any]:
    answer = answer.strip()
    if answer.lower() == "q":
        raise Quit
    if answer == "":
        return {"value": prefill, "verified": prefill is not None}
    if answer == "?":
        return {"value": prefill, "verified": False}
    if answer == "-":
        return {"value": None, "verified": True}
    return {"value": parse_field(field, answer), "verified": True}


def parse_item(line: str) -> dict[str, Any]:
    """'ÇAY 500G; 139,90' -> {"name": "ÇAY 500G", "total_minor": 13990}."""
    name, _, price = line.rpartition(";")
    minor = to_minor(price)
    if not name.strip() or minor is None:
        raise ValueError(line)
    return {"name": name.strip(), "total_minor": minor}


def label(
    receipt: Receipt,
    ask: Callable[[str], str],
    say: Callable[[str], None],
) -> dict[str, Any]:
    prefill = receipt.meta.get("prefill", {})
    old = receipt.gold or {}
    say(f"\n=== {receipt.rid} ({receipt.meta.get('source', '?')}) ===")
    for number, line in enumerate(receipt.masked_text.splitlines(), start=1):
        say(f"{number:3} | {line}")
    say(HELP)

    gold: dict[str, Any] = {"fields": {}, "items": {}, "s5_allowed": False}
    for field, prompt in FIELD_PROMPTS.items():
        start = old.get("fields", {}).get(field, {}).get("value", prefill.get(field))
        mark = "" if old.get("fields", {}).get(field, {}).get("verified") else " [doğrulanmadı]"
        while True:
            answer = ask(f"{prompt}: {show_value(field, start)}{mark} > ")
            try:
                gold["fields"][field] = answer_field(field, start, answer)
                break
            except ValueError:
                say("Okunamadı, tekrar yaz.")

    items = old.get("items", {}).get("value", prefill.get("items", []))
    say("Kalemler [doğrulanmadı]:" if not old.get("items", {}).get("verified") else "Kalemler:")
    for item in items:
        say(f"   - {item['name']}; {show_value('total_minor', item.get('total_minor'))}")
    answer = ask("Kalemler: Enter = doğru, d = yeniden yaz, - = kalem yok, ? = geç > ").strip()
    if answer.lower() == "q":
        raise Quit
    if answer == "":
        gold["items"] = {"value": items, "verified": True}
    elif answer == "-":
        gold["items"] = {"value": [], "verified": True}
    elif answer.lower() == "d":
        typed: list[dict[str, Any]] = []
        say("Her satıra 'AD; FİYAT' yaz, bitince boş satır.")
        while True:
            line = ask("  kalem > ").strip()
            if not line:
                break
            try:
                typed.append(parse_item(line))
            except ValueError:
                say("Okunamadı: 'AD; FİYAT' biçiminde yaz.")
        gold["items"] = {"value": typed, "verified": True}
    else:
        gold["items"] = {"value": items, "verified": False}

    s5 = ask(
        "Bu fişin FOTOĞRAFI (maskesiz) S5 deneyi için ücretsiz modele gönderilebilir mi? "
        "Kişisel bilgi yoksa e (e/H) > "
    )
    gold["s5_allowed"] = s5.strip().lower() in ("e", "evet")
    return gold


def save(receipt: Receipt, gold: dict[str, Any]) -> None:
    (receipt.folder / "gold.json").write_text(
        json.dumps(gold, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    receipt.gold = gold


def needs_work(receipt: Receipt) -> bool:
    gold = receipt.gold
    if not gold:
        return True
    unverified = [f for f, e in gold.get("fields", {}).items() if not e.get("verified")]
    return bool(unverified) or not gold.get("items", {}).get("verified")
