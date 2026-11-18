"""Generate SYNTHETIC test samples for the P04 capture pipeline (no real data, ever).

Everything printed on these images is made up: the names, phone numbers, IBANs and card numbers
are fake or public test values. The output goes to ai/datasets/synthetic/, which is git-ignored.

Run (from the repo root):

    uv run --with pillow --with "qrcode[pil]" python ai/experiments/make_synthetic_samples.py

Files written:
    receipt_market.jpg       thermal-receipt look, Turkish text, a fake phone + customer name
    receipt_rotated.jpg      the same receipt with EXIF orientation 6 (phone held sideways)
    receipt_gib_qr.jpg       an e-Arşiv style receipt with a GİB QR code (buyer TCKN inside it)
    bank_screenshot.jpg      a made-up banking-app list with fake IBAN, balance and card number
    invoice_2pages.pdf       a two-page PDF invoice (rasterised pages)
    not_a_receipt.jpg        a photo-like gradient without any text (must give "no text found")
"""

from __future__ import annotations

import json
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "datasets" / "synthetic"
FONT_DIR = Path("C:/Windows/Fonts")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def draw_lines(img: Image.Image, lines: list[tuple[str, str, int]], x: int = 40, y: int = 40, gap: int = 10):
    draw = ImageDraw.Draw(img)
    for text, face, size in lines:
        f = font(face, size)
        draw.text((x, y), text, font=f, fill="black")
        y += size + gap
    return y


def receipt_lines() -> list[tuple[str, str, int]]:
    mono, bold = "consola.ttf", "consolab.ttf"
    return [
        ("ÖRNEK MARKET TİC. LTD. ŞTİ.", bold, 34),
        ("Vergi No: 1234567890 (örnek)", mono, 28),
        ("Tel: 0532 123 45 67", mono, 28),
        ("Tarih: 14.11.2026   Saat: 18:42", mono, 28),
        ("Fiş No: 004512", mono, 28),
        ("Müşteri: Ayşe Örnek", mono, 28),
        ("-" * 38, mono, 28),
        ("SÜT 1L                      69,90", mono, 28),
        ("EKMEK                       12,50", mono, 28),
        ("ŞEKER 1KG                   48,00", mono, 28),
        ("ÇAY 500G                   139,90", mono, 28),
        ("-" * 38, mono, 28),
        ("TOPLAM                     270,30", bold, 32),
        ("KDV %10                     24,57", mono, 28),
        ("KART: 4111 1111 1111 1111", mono, 28),
        ("TEŞEKKÜRLER", bold, 32),
    ]


def make_receipt(path: Path, rotated: bool = False) -> None:
    img = Image.new("RGB", (900, 760), "white")
    draw_lines(img, receipt_lines())
    if rotated:
        # Store the pixels turned 90 degrees and tell viewers to rotate them back (EXIF 6).
        img = img.rotate(90, expand=True)
        exif = Image.Exif()
        exif[0x0112] = 6
        img.save(path, quality=92, exif=exif)
    else:
        img.save(path, quality=92)


def make_gib_receipt(path: Path) -> None:
    payload = {
        "ettn": "11111111-2222-3333-4444-555555555555",
        "vkntckn": "1234567890",
        "avkntckn": "12345678901",  # the BUYER's identity number: must be removed by the app
        "senaryo": "EARSIVFATURA",
        "tarih": "2026-11-14",
        "no": "ABC2026000000123",
        "vergidahil": "270.30",
        "odenecek": "270.30",
        "paraBirimi": "TRY",
    }
    qr = qrcode.make(json.dumps(payload, separators=(",", ":"))).convert("RGB").resize((340, 340))
    img = Image.new("RGB", (900, 1180), "white")
    y = draw_lines(img, receipt_lines())
    img.paste(qr, (40, y + 30))
    img.save(path, quality=92)


def make_bank_screenshot(path: Path) -> None:
    img = Image.new("RGB", (900, 1500), "#F2F4F7")
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 900, 150), fill="#0E5E57")
    draw.text((40, 50), "Hesap Hareketleri", font=font("arialbd.ttf", 48), fill="white")
    rows = [
        ("Kullanılabilir Bakiye: 12.345,67 TL", 40),
        ("IBAN: TR33 0006 1005 1978 6457 8413 26", 36),
        ("Kart No: 4111 1111 1111 1111", 36),
        ("Hesap Sahibi: Ayşe Örnek", 36),
        ("", 20),
        ("A101 MAĞAZACILIK        -270,30 TL", 38),
        ("14 Kasım 2026", 30),
        ("", 20),
        ("TRENDYOL ONLINE         -1.349,90 TL", 38),
        ("12 Kasım 2026", 30),
        ("", 20),
        ("MIGROS TİCARET          -418,25 TL", 38),
        ("10 Kasım 2026", 30),
    ]
    y = 190
    for text, size in rows:
        draw.text((40, y), text, font=font("arial.ttf", size), fill="#16211F")
        y += size + 22
    img.save(path, quality=92)


def make_pdf(path: Path) -> None:
    pages = []
    for number in (1, 2):
        page = Image.new("RGB", (1240, 1754), "white")  # A4 at 150 dpi
        lines = [
            ("ÖRNEK ELEKTRONİK A.Ş.", "arialbd.ttf", 54),
            (f"e-Arşiv Fatura - Sayfa {number}/2", "arial.ttf", 38),
            ("Fatura No: ABC2026000000456", "arial.ttf", 38),
            ("Tarih: 05.11.2026", "arial.ttf", 38),
            ("Sayın Mehmet Örnek", "arial.ttf", 38),
        ]
        if number == 1:
            lines += [
                ("Kulaklık Bluetooth          1 adet      2.499,00 TL", "arial.ttf", 38),
                ("Ödenecek Tutar: 2.499,00 TL", "arialbd.ttf", 42),
            ]
        else:
            lines += [("Garanti ve iade koşulları bu sayfadadır.", "arial.ttf", 38)]
        draw_lines(page, lines, x=80, y=100, gap=24)
        pages.append(page)
    pages[0].save(path, save_all=True, append_images=pages[1:], resolution=150)


def make_no_text(path: Path) -> None:
    img = Image.new("RGB", (800, 800))
    px = img.load()
    for yy in range(800):
        for xx in range(800):
            px[xx, yy] = (xx // 4, yy // 4, 128)
    img.save(path, quality=90)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    make_receipt(OUT / "receipt_market.jpg")
    make_receipt(OUT / "receipt_rotated.jpg", rotated=True)
    make_gib_receipt(OUT / "receipt_gib_qr.jpg")
    make_bank_screenshot(OUT / "bank_screenshot.jpg")
    make_pdf(OUT / "invoice_2pages.pdf")
    make_no_text(OUT / "not_a_receipt.jpg")
    for file in sorted(OUT.iterdir()):
        print(f"{file.name}  {file.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
