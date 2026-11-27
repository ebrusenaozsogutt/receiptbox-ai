"""E4 privacy (spec 19): synthetic receipt and bank texts with injected personal data, masked by
the app's own Dart masker (mobile/tool/mask_jsonl.dart), scored per PII type.

Every value is made up and generated from a fixed seed. Personal data: Turkish names (after the
masker's keywords "Sayın", "Ad Soyad", "Kart Sahibi", "Müşteri" and, separately, without a
keyword), IBANs with valid check digits, Luhn-valid card numbers in several layouts and partly
starred ones, TCKNs with a valid checksum, mobile and landline phones, e-mails, balance / limit /
account lines. Look-alikes that must stay readable: totals, dates, times, 11-digit numbers with an
invalid TCKN checksum, 16-digit numbers failing Luhn, EAN-13 barcodes, 10-digit tax numbers,
receipt numbers.

A personal value counts as masked when its text no longer appears in the output (a name: neither
the first name nor the surname appears). A look-alike counts as a false positive when its text no
longer appears.
"""

import json
import random
import shutil
import subprocess
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from rbx_eval import MOBILE
from rbx_eval.metrics import bootstrap, rate

FIRST_NAMES = (
    "Ayşe Mehmet Zeynep Mustafa Elif Ahmet Fatma Emre Büşra Can Özge İbrahim Şule Çağla Gökhan "
    "Merve Hüseyin Esra Oğuz Gülşen Burak Ebru İrem Serkan Hatice Ümit Deniz Kübra Onur Sibel"
).split()
SURNAMES = (
    "Yılmaz Kaya Demir Şahin Çelik Yıldız Öztürk Aydın Özdemir Arslan Doğan Kılıç Aslan Çetin "
    "Koç Kurt Özkan Şimşek Polat Erdoğan Güneş Aksoy Tekin Uçar Karaca Bulut Ünal Korkmaz"
).split()
MERCHANTS = ["MİGROS", "A101", "BİM", "ŞOK", "CARREFOURSA", "TEKNOSA", "LC WAİKİKİ", "GRATİS"]
ITEMS = ["SÜT 1L", "EKMEK", "YUMURTA 10LU", "DOMATES KG", "PEYNİR", "ÇAY 1KG", "DETERJAN", "SU 5L"]
NAME_KEYWORDS = ("Sayın", "Ad Soyad:", "Kart Sahibi:", "Müşteri:")
FREE_NAME_LABELS = ("Kasiyer:", "Teslim alan:", "Hazırlayan:")

# Turkish labels of the types, for the report.
TYPE_LABELS = {
    "name_keyword": "İsim (anahtar kelimeli)",
    "name_free": "İsim (anahtar kelimesiz)",
    "iban": "IBAN",
    "card": "Kart numarası",
    "card_partial": "Kısmen maskeli kart",
    "tckn": "TCKN",
    "phone": "Telefon",
    "email": "E-posta",
    "balance": "Bakiye / limit / hesap satırı",
    "total": "Toplam tutar",
    "date": "Tarih",
    "time": "Saat",
    "tckn_invalid": "11 hane, geçersiz TCKN",
    "luhn_invalid": "16 hane, Luhn'dan geçmeyen",
    "ean13": "EAN-13 barkod",
    "tax_number": "10 haneli vergi no (VKN)",
    "receipt_no": "Fiş / Z numarası",
}
PII_TYPES = (
    "name_keyword", "name_free", "iban", "card", "card_partial", "tckn", "phone", "email",
    "balance",
)  # fmt: skip


@dataclass
class Span:
    type: str
    value: str
    pii: bool
    names: list[str] = field(default_factory=list)  # first name and surname, for names
    noisy: bool = False  # an OCR-like error was put into the value


@dataclass
class Sample:
    id: str
    text: str
    bank: bool
    spans: list[Span]


# ---- valid identifiers ----------------------------------------------------------------------


def luhn_check_digit(body: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def luhn_valid(number: str) -> bool:
    return luhn_check_digit(number[:-1]) == number[-1]


def tckn_valid(number: str) -> bool:
    if len(number) != 11 or not number.isdigit() or number[0] == "0":
        return False
    d = [int(c) for c in number]
    tenth = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    return d[9] == tenth and d[10] == sum(d[:10]) % 10


def iban_check_digits(bban: str) -> str:
    rearranged = bban + "2927" + "00"  # T=29, R=27
    return f"{98 - int(rearranged) % 97:02d}"


def iban_valid(iban: str) -> bool:
    compact = iban.replace(" ", "")
    rearranged = compact[4:] + "2927" + compact[2:4]
    return compact.startswith("TR") and len(compact) == 26 and int(rearranged) % 97 == 1


def ean13_check(body: str) -> str:
    total = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(body))
    return str((10 - total % 10) % 10)


class Faker:
    """Made-up values from one seeded random generator."""

    def digits(self, n: int, *, first_nonzero: bool = False) -> str:
        out = [str(self.r.randint(1 if first_nonzero else 0, 9))]
        out += [str(self.r.randint(0, 9)) for _ in range(n - 1)]
        return "".join(out)

    def __init__(self, seed: int) -> None:
        self.r = random.Random(seed)
        self.used_names: set[str] = set()  # within one text: no shared first name or surname

    def name(self) -> tuple[str, str]:
        while True:
            first, last = self.r.choice(FIRST_NAMES), self.r.choice(SURNAMES)
            if first not in self.used_names and last not in self.used_names:
                self.used_names.update((first, last))
                return first, last

    def iban(self) -> str:
        bban = self.digits(5) + "0" + self.digits(16)
        compact = "TR" + iban_check_digits(bban) + bban
        if self.r.random() < 0.6:
            return " ".join(compact[i : i + 4] for i in range(0, len(compact), 4))
        return compact

    def card_number(self) -> str:
        prefix = self.r.choice(["4", "5", "9792"])
        body = prefix + self.digits(15 - len(prefix))
        return body + luhn_check_digit(body)

    def card(self) -> str:
        number = self.card_number()
        layout = self.r.choice(["spaces", "dashes", "compact"])
        if layout == "compact":
            return number
        sep = " " if layout == "spaces" else "-"
        return sep.join(number[i : i + 4] for i in range(0, 16, 4))

    def card_partial(self) -> str:
        number = self.card_number()
        if self.r.random() < 0.5:
            return f"{number[:4]} **** **** {number[-4:]}"
        return f"{number[:6]}******{number[-4:]}"

    def tckn(self, *, valid: bool = True) -> str:
        while True:
            d = [int(c) for c in self.digits(9, first_nonzero=True)]
            tenth = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
            eleventh = (sum(d) + tenth) % 10
            number = "".join(map(str, d)) + str(tenth) + str(eleventh)
            if valid:
                return number
            broken = number[:-1] + str((eleventh + self.r.randint(1, 9)) % 10)
            if not tckn_valid(broken):
                return broken

    def phone(self) -> str:
        operator = self.r.choice(["532", "533", "505", "542", "555", "506"])
        a, b, c = self.digits(3), self.digits(2), self.digits(2)
        return self.r.choice(
            [
                f"+90 {operator} {a} {b} {c}",
                f"0{operator} {a} {b} {c}",
                f"0{operator}{a}{b}{c}",
                f"0 ({operator}) {a} {b} {c}",
                f"0212 {a} {b} {c}",
            ]
        )

    def email(self, first: str, last: str) -> str:
        fold = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
        user = f"{first}.{last}".translate(fold).lower() + str(self.r.randint(1, 99))
        return f"{user}@{self.r.choice(['gmail.com', 'outlook.com', 'hotmail.com', 'example.com'])}"

    def amount(self) -> str:
        lira = self.r.randint(1, 25000)
        return f"{lira:,}".replace(",", ".") + f",{self.r.randint(0, 99):02d}"

    def luhn_invalid16(self) -> str:
        while True:
            number = self.digits(16, first_nonzero=True)
            if not luhn_valid(number):
                return number

    def ean13(self) -> str:
        body = "869" + self.digits(9)
        return body + ean13_check(body)

    def tax_number(self) -> str:
        return self.digits(10, first_nonzero=True)


# ---- OCR noise ---------------------------------------------------------------------------------

NOISY_TYPES = ("iban", "card", "tckn", "phone")


def ocr_noise(value: str, r: random.Random) -> str:
    """One error OCR makes on printed numbers: a 0 read as O, a stray space inside a digit group,
    or the separators lost. Always changes the value."""
    choices = []
    if "0" in value:
        choices.append("o_for_zero")
    if any(c in value for c in " -"):
        choices.append("drop_separators")
    choices.append("stray_space")
    kind = r.choice(choices)
    if kind == "o_for_zero":
        positions = [i for i, c in enumerate(value) if c == "0"]
        i = r.choice(positions)
        return value[:i] + "O" + value[i + 1 :]
    if kind == "drop_separators":
        return value.replace(" ", "").replace("-", "")
    digits = [i for i, c in enumerate(value) if c.isdigit() and 0 < i < len(value) - 1]
    i = r.choice(digits)
    return value[:i] + " " + value[i:]


# ---- texts ------------------------------------------------------------------------------------


def _pii_line(f: Faker, kind: str) -> tuple[str, Span]:
    first, last = f.name()
    if kind == "name_keyword":
        label = f.r.choice(NAME_KEYWORDS)
        return f"{label} {first} {last}", Span(kind, f"{first} {last}", True, [first, last])
    if kind == "name_free":
        label = f.r.choice(FREE_NAME_LABELS)
        return f"{label} {first} {last}", Span(kind, f"{first} {last}", True, [first, last])
    if kind == "iban":
        value = f.iban()
        return f"IBAN: {value}", Span(kind, value, True)
    if kind == "card":
        value = f.card()
        return f"KART NO: {value}", Span(kind, value, True)
    if kind == "card_partial":
        value = f.card_partial()
        return f"Kart: {value}", Span(kind, value, True)
    if kind == "tckn":
        value = f.tckn()
        return f"TCKN: {value}", Span(kind, value, True)
    if kind == "phone":
        value = f.phone()
        return f"Tel: {value}", Span(kind, value, True)
    if kind == "email":
        value = f.email(first, last)
        return f"E-posta: {value}", Span(kind, value, True)
    if kind == "balance":
        value = f.amount()
        label = f.r.choice(["Bakiye", "Kullanılabilir Limit", "Toplam Borç", "Hesap No"])
        if label == "Hesap No":
            value = f.digits(8, first_nonzero=True)
            return f"{label}: {value}", Span(kind, value, True)
        return f"{label}: {value} TL", Span(kind, value, True)
    raise ValueError(kind)


def _look_alike_line(f: Faker, kind: str) -> tuple[str, Span]:
    if kind == "total":
        value = f.amount()
        return f"TOPLAM *{value}", Span(kind, value, False)
    if kind == "date":
        value = f"{f.r.randint(1, 28):02d}.{f.r.randint(1, 12):02d}.{f.r.choice([2025, 2026])}"
        return f"TARİH: {value}", Span(kind, value, False)
    if kind == "time":
        value = f"{f.r.randint(0, 23):02d}:{f.r.randint(0, 59):02d}"
        return f"SAAT: {value}", Span(kind, value, False)
    if kind == "tckn_invalid":
        value = f.tckn(valid=False)
        return f"REF: {value}", Span(kind, value, False)
    if kind == "luhn_invalid":
        value = f.luhn_invalid16()
        return f"İşlem No: {value}", Span(kind, value, False)
    if kind == "ean13":
        value = f.ean13()
        return f"{value} {f.r.choice(ITEMS)}", Span(kind, value, False)
    if kind == "tax_number":
        value = f.tax_number()
        return f"VKN: {value}", Span(kind, value, False)
    if kind == "receipt_no":
        value = f"{f.r.randint(1, 9999):04d}"
        return f"FİŞ NO: {value}", Span(kind, value, False)
    raise ValueError(kind)


LOOK_ALIKE_TYPES = tuple(t for t in TYPE_LABELS if t not in PII_TYPES)


def generate(n: int, seed: int = 2026, noise_share: float = 0.2) -> list[Sample]:
    """`n` texts; every PII type and look-alike type appears in roughly the same number of texts."""
    f = Faker(seed)
    samples = []
    for i in range(n):
        f.used_names.clear()
        bank = i % 4 == 3  # a quarter look like bank screens (masked with bank=True)
        lines = (
            ["GARANTİ BBVA", "Kart Hareketleri"] if bank else [f.r.choice(MERCHANTS), "TEŞEKKÜRLER"]
        )
        spans: list[Span] = []
        body: list[str] = []
        pii_kinds = f.r.sample(PII_TYPES, k=f.r.randint(2, 4))
        look_kinds = f.r.sample(LOOK_ALIKE_TYPES, k=f.r.randint(3, 5))
        for kind in pii_kinds:
            line, span = _pii_line(f, kind)
            if kind in NOISY_TYPES and f.r.random() < noise_share:
                noisy = ocr_noise(span.value, f.r)
                line = line.replace(span.value, noisy)
                span = Span(kind, noisy, True, noisy=True)
            body.append(line)
            spans.append(span)
        for kind in look_kinds:
            line, span = _look_alike_line(f, kind)
            body.append(line)
            spans.append(span)
        for _ in range(f.r.randint(1, 3)):
            body.append(f"{f.r.choice(ITEMS)} {f.r.randint(1, 3)} x *{f.amount()}")
        f.r.shuffle(body)
        samples.append(Sample(f"e4-{i:04d}", "\n".join(lines + body), bank, spans))
    return samples


# ---- the masker and the scores ---------------------------------------------------------------


def run_masker(samples: list[Sample], workdir: Path) -> dict[str, str]:
    """Masks every text with the app's Dart masker; returns id -> masked text."""
    source, target = workdir / "e4_input.jsonl", workdir / "e4_masked.jsonl"
    with source.open("w", encoding="utf-8") as handle:
        for s in samples:
            handle.write(
                json.dumps({"id": s.id, "text": s.text, "bank": s.bank}, ensure_ascii=False)
            )
            handle.write("\n")
    subprocess.run(
        [shutil.which("dart") or "dart", "run", "tool/mask_jsonl.dart", str(source), str(target)],
        cwd=MOBILE,
        check=True,
        capture_output=True,
        shell=False,
    )
    masked = {}
    for line in target.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        masked[item["id"]] = item["masked"]
    return masked


def is_removed(span: Span, masked: str) -> bool:
    if span.names:
        return all(name not in masked for name in span.names)
    return span.value not in masked


def score(samples: list[Sample], masked: dict[str, str]) -> dict[str, Any]:
    outcomes: dict[str, list[bool]] = defaultdict(list)
    rows = []
    for s in samples:
        out = masked[s.id]
        for span in s.spans:
            removed = is_removed(span, out)
            outcomes[span.type].append(removed)
            rows.append({"id": s.id, "bank": s.bank, **asdict(span), "removed": removed})

    def estimate(flags: list[bool]) -> dict[str, float]:
        return bootstrap(flags, rate, resamples=2000, seed=7).as_dict()

    per_type = []
    for kind, label in TYPE_LABELS.items():
        flags = outcomes.get(kind, [])
        pii = kind in PII_TYPES
        per_type.append(
            {
                "type": kind,
                "label": label,
                "pii": pii,
                "n": len(flags),
                "removed": sum(flags),
                # PII: recall = removed share. Look-alike: false-positive rate = removed share.
                "metric": "recall" if pii else "false_positive_rate",
                **estimate(flags),
            }
        )
    noisy_rows = [r for r in rows if r["pii"] and r["type"] in NOISY_TYPES]
    by_noise = []
    for kind in NOISY_TYPES:
        for noisy in (False, True):
            flags = [r["removed"] for r in noisy_rows if r["type"] == kind and r["noisy"] == noisy]
            by_noise.append(
                {
                    "type": kind,
                    "label": TYPE_LABELS[kind],
                    "variant": "ocr_noise" if noisy else "clean",
                    "n": len(flags),
                    "removed": sum(flags),
                    **estimate(flags),
                }
            )
    all_pii = [f for k in PII_TYPES for f in outcomes.get(k, [])]
    keyword_pii = [f for k in PII_TYPES if k != "name_free" for f in outcomes.get(k, [])]
    all_look = [f for k in LOOK_ALIKE_TYPES for f in outcomes.get(k, [])]
    texts_with_leak = [
        any(not r["removed"] for r in rows if r["id"] == s.id and r["pii"]) for s in samples
    ]
    return {
        "samples": len(samples),
        "pii_values": len(all_pii),
        "look_alike_values": len(all_look),
        "recall_all": estimate(all_pii),
        "recall_without_free_names": estimate(keyword_pii),
        "false_positive_rate": estimate(all_look),
        "texts_with_a_leak": estimate(texts_with_leak),
        "per_type": per_type,
        "noise": by_noise,
        "rows": rows,
    }
