## Bank hints: Garanti BBVA (also the Bonus cards: Bonus, Bonus Dijital, Bonus Business Troy)

- **Card transaction lists** ("Dönem İçi", "Son Dönem İçi Hareketleri", "Gerçekleşen Hareketler"):
  every row has a **category word** (`Market`, `Elektronik`, `Eğitim`, `Ulaşım`, `Vergi`,
  `Kişisel Hizmet`, `Akaryakıt`, `Kart Ödemesi`) first, the amount on the same line, and the
  **merchant** on the second line (`TRENDYOL.COM`, `DERESALLAR GIDA VE İHTİYA`). The merchant is the
  second line, never the category word. `Market (İade)` means a refund.
- The **date** of a row is printed as a day number, then a short month, then the year, often on
  three separate lines (`12`, `Kas`, `2026`). Return `12 Kas 2026`.
- Amounts: `-16.128,33 TL` money spent (minus), `+160.855,99 TL` money that came back (plus).
- The **installment marker** is printed at the end of the merchant line, in parentheses: `(2/3)`,
  `(3/3)`. Return it as `installment_text`.
- Green buttons under a row (`Ek Taksit`, `Ertele / Taksitlendir`, `Taksitlendir`, `Tekrarla`) are
  buttons, not part of the row.
- A line such as `0,38 Bonus` under a row is a points note. A row whose amount is `-27,84 Bonus`
  (`Ödül Kullanımı`) is a points row: skip it.
- `Kart Ödemesi` with a `+` amount and a description such as `Cep Şube Ödeme` or `ATM ÖDEME` is a
  payment of the card bill: return it as it is (the server sets it aside).
- **POS slip** ("Dijital Slip": merchant block, `K.N: **** **** **** dddd`, `TAKSİTLİ SATIŞ
  TUTARI`, `ÖDEME PLANI`, `3 TAKSİTLİ X 56.000,00 TL`): it is ONE transaction. `merchant_raw` is
  the merchant name at the top of the slip, `amount_text` is the **sale amount** (`TAKSİTLİ SATIŞ
  TUTARI` or `TUTAR`), NOT the amount of one installment, `date_text` is the date printed in the
  slip (`06/11/2026`), `installment_text` is `3 TAKSİTLİ`.
- **Account movements** ("Hesap Hareketleri" with `İşlem Sonu Bakiye` lines) are not card rows.
