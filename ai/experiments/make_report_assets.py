"""Tables (Markdown) and figures (PNG) with Turkish captions for the report, from the LATEST run
of each experiment, into docs/report_assets/. Only real runs are used; an experiment without a
run (or with only a synthetic pipeline check) gets no asset.

    cd ai/experiments && uv run python make_report_assets.py
"""

import csv
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
from rbx_eval import REPORT_ASSETS  # noqa: E402
from rbx_eval.runs import latest_run  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402

GROUP_TR = {
    "category_period": "Kategori + dönem",
    "merchant": "Tek mağaza",
    "relative_period": "Göreli dönem (geçen yıl, son 3 ay)",
    "comparison": "Karşılaştırma",
    "ranking": "En pahalı / sayım",
    "products": "Ürün, garanti, iade, belge",
    "installments": "Taksit",
    "no_data": "Kayıtta olmayan",
    "out_of_scope": "Kapsam dışı",
}


def pct(value: float) -> str:
    return f"%{value * 100:.1f}".replace(".", ",")


def ci(entry: dict[str, float]) -> str:
    return f"{pct(entry['value'])} [{pct(entry['ci_low'])} – {pct(entry['ci_high'])}]"


def write(name: str, text: str) -> Path:
    REPORT_ASSETS.mkdir(parents=True, exist_ok=True)
    path = REPORT_ASSETS / name
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return path


# ---- E4 -----------------------------------------------------------------------------------------


def e4_assets() -> list[str]:
    run = latest_run("e4")
    if run is None:
        return []
    summary = json.loads((run / "summary.json").read_text("utf-8"))
    rows = summary["per_type"]
    pii = [r for r in rows if r["pii"]]
    look = [r for r in rows if not r["pii"]]
    lines = [
        "**Tablo E4-1. Kişisel veri maskeleme başarısı (recall), türe göre.** "
        f"{summary['samples']} sentetik fiş / banka metni, {summary['pii_values']} kişisel değer; "
        "maskeleyici: uygulamanın kendi Dart kodu (cihazda çalışan). Köşeli parantez: %95 bootstrap "
        "güven aralığı.",
        "",
        "| Tür | n | Maskelenen | Recall [%95 GA] |",
        "|---|---:|---:|---|",
    ]
    lines += [f"| {r['label']} | {r['n']} | {r['removed']} | {ci(r)} |" for r in pii]
    lines += [
        f"| **Tümü** | {summary['pii_values']} | | {ci(summary['recall_all'])} |",
        f"| Tümü, anahtar kelimesiz isimler hariç | | | {ci(summary['recall_without_free_names'])} |",
        "",
        "**Tablo E4-2. Kişisel olmayan benzer değerlerde yanlış maskeleme oranı.** "
        f"{summary['look_alike_values']} değer.",
        "",
        "| Tür | n | Yanlışlıkla maskelenen | Yanlış pozitif oranı [%95 GA] |",
        "|---|---:|---:|---|",
    ]
    lines += [f"| {r['label']} | {r['n']} | {r['removed']} | {ci(r)} |" for r in look]
    lines += [
        f"| **Tümü** | {summary['look_alike_values']} | | {ci(summary['false_positive_rate'])} |"
    ]
    noise = summary.get("noise", [])
    if noise:
        lines += [
            "",
            "**Tablo E4-3. OCR hatası olan ve olmayan değerlerde maskeleme başarısı.** OCR hatası: "
            "0 yerine O, rakam grubunun içinde fazladan boşluk ya da ayraçların kaybolması "
            f"(değerlerin %{summary['config']['noise_share'] * 100:.0f}'si).",
            "",
            "| Tür | Değer | n | Recall [%95 GA] |",
            "|---|---|---:|---|",
        ]
        variant = {"clean": "temiz", "ocr_noise": "OCR hatalı"}
        lines += [f"| {r['label']} | {variant[r['variant']]} | {r['n']} | {ci(r)} |" for r in noise]
    lines += [
        "",
        "Not: Metinler sentetiktir ve değer biçimleri maskeleyicinin kurallarını bilen biri "
        "tarafından üretilmiştir; temiz değerlerde %100'e yakın sonuçlar bu yüzden iyimserdir. "
        "OCR hatalı satırlar gerçek hayattaki zayıflığı gösterir. Anahtar kelimesiz isimler "
        "(ör. 'Kasiyer: …') tasarım gereği maskelenmez (spec 15.1: isimler yalnızca 'Sayın', "
        "'Ad Soyad', 'Kart Sahibi', 'Müşteri' sonrasında).",
    ]
    write("e4_privacy.md", "\n".join(lines))

    figure, axis = plt.subplots(figsize=(7, 4))
    labels = [r["label"] for r in pii]
    values = [r["value"] * 100 for r in pii]
    errors = [
        [(r["value"] - r["ci_low"]) * 100 for r in pii],
        [(r["ci_high"] - r["value"]) * 100 for r in pii],
    ]
    axis.barh(labels, values, xerr=errors, color="#0E5E57")
    axis.set_xlim(0, 105)
    axis.set_xlabel("Maskelenen kişisel değer (%)")
    axis.set_title("E4: türe göre maskeleme başarısı (%95 GA)")
    axis.invert_yaxis()
    figure.tight_layout()
    figure.savefig(REPORT_ASSETS / "e4_recall_by_type.png", dpi=150)
    plt.close(figure)
    return ["e4_privacy.md", "e4_recall_by_type.png"]


# ---- E3 -----------------------------------------------------------------------------------------


def e3_assets() -> list[str]:
    run = latest_run("e3")
    if run is None:
        return []
    summary = json.loads((run / "summary.json").read_text("utf-8"))
    rows = list(csv.DictReader((run / "questions.csv").open(encoding="utf-8")))
    partial = (
        ""
        if summary["complete"]
        else f" **Ara sonuç: {summary['asked']}/{summary['planned_questions']} soru** "
        "(ücretsiz kotanın günlük sınırı; kalan sorular sonraki günlerde aynı önbellekle "
        "tamamlanır)."
    )
    lat = summary["latency_ms"]
    metrics = [
        ("Araç seçimi doğruluğu", summary["tool_selection_accuracy"]),
        ("Cevap doğruluğu (tüm sorular)", summary["answer_correct"]),
        ("Sayısal doğruluk (sayı içeren altın cevaplar)", summary["numeric_correctness"]),
        ("Doğru 'kayıt yok' cevabı", summary["no_data_correct"]),
        ("Kapsam dışı soruyu doğru geri çevirme", summary["out_of_scope_correct"]),
        ("Halüsinasyon: modelin İLK cevabında araçta olmayan sayı", summary["first_answer_hallucination_rate"]),
        ("Son cevapta araçta olmayan sayı", summary["final_answer_unsupported_rate"]),
    ]  # fmt: skip
    lines = [
        "**Tablo E3-1. Asistan değerlendirmesi.** Model: "
        f"{summary['config']['model']} (ücretsiz plan), tohumlanmış değerlendirme veritabanı, "
        "bugün = 26.11.2026; altın cevaplar uygulamadan bağımsız SQL ile hesaplandı. "
        f"Köşeli parantez: %95 bootstrap güven aralığı.{partial}",
        "",
        "| Ölçüt | n | Değer [%95 GA] |",
        "|---|---:|---|",
    ]
    for name, entry in metrics:
        if entry["n"]:
            lines.append(f"| {name} | {entry['n']} | {ci(entry)} |")
        else:
            lines.append(f"| {name} | 0 | (henüz soru yok) |")
    lines += [
        f"| Cevap süresi (canlı istekler) | {lat['n']} | medyan {lat['median'] / 1000:.1f} sn, "
        f"p95 {lat['p95'] / 1000:.1f} sn |".replace(".", ","),
        "",
        "**Tablo E3-2. Soru gruplarına göre sonuç.**",
        "",
        "| Grup | n | Doğru araç | Doğru cevap |",
        "|---|---:|---:|---:|",
    ]
    for g in summary["by_group"]:
        lines.append(
            f"| {GROUP_TR.get(g['group'], g['group'])} | {g['n']} | {g['tool_ok']} | {g['correct']} |"
        )
    wrong = [r for r in rows if r["correct"] != "True"]
    if wrong:
        lines += [
            "",
            "**Tablo E3-3. Yanlış cevaplar (hata analizi).**",
            "",
            "| Soru | Çağrılan araç ve argümanlar | Cevap |",
            "|---|---|---|",
        ]
        for r in wrong:
            args = r["tool_args"].replace("|", "/")
            lines.append(f"| {r['question']} | {r['tools_called']} `{args}` | {r['answer']} |")
    write("e3_assistant.md", "\n".join(lines))

    figure, axis = plt.subplots(figsize=(7, 4))
    groups = summary["by_group"]
    names = [GROUP_TR.get(g["group"], g["group"]) for g in groups]
    axis.barh(names, [g["correct"] / g["n"] * 100 for g in groups], color="#0E5E57")
    axis.set_xlim(0, 105)
    axis.set_xlabel("Doğru cevap (%)")
    axis.set_title(f"E3: gruplara göre doğru cevap ({summary['asked']} soru)")
    axis.invert_yaxis()
    figure.tight_layout()
    figure.savefig(REPORT_ASSETS / "e3_correct_by_group.png", dpi=150)
    plt.close(figure)
    return ["e3_assistant.md", "e3_correct_by_group.png"]


def index(made: list[str]) -> None:
    captions: dict[str, Any] = {
        "e3_assistant.md": "E3 asistan: ölçütler, gruplar, hata analizi (Tablo E3-1 – E3-3)",
        "e3_correct_by_group.png": "E3 asistan: gruplara göre doğru cevap oranı",
        "e4_privacy.md": "E4 gizlilik: türe göre recall, yanlış pozitif, OCR hatası (Tablo E4-1 – E4-3)",
        "e4_recall_by_type.png": "E4 gizlilik: türe göre maskeleme başarısı ve %95 GA",
    }
    lines = [
        "# Rapor tabloları ve şekilleri (P15)",
        "",
        "`ai/experiments/make_report_assets.py` ile her deneyin son gerçek çalışmasından üretilir. "
        "Elle yazılmış sayı yoktur. E1 (fiş okuma) ve E2 (eşleştirme) gerçek etiketli veri "
        "gelince eklenecek.",
        "",
    ]
    lines += [f"- `{name}`: {captions.get(name, '')}" for name in made]
    write("README.md", "\n".join(lines))


def main() -> None:
    made = e3_assets() + e4_assets()
    index(made)
    print("written:", ", ".join(made))


if __name__ == "__main__":
    main()
