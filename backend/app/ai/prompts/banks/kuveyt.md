## Bank hints: Kuveyt Türk

- **Statement and period lists** ("Ekstre", "Dönem İçi Harcamalar"): each row is a **date** in the
  form `20.10.2026`, a small category icon (no text), the **merchant** on the next one or two lines
  (`PAYCELL/TRENDYOL ISTANBUL TR`, `MİGROS-5M KULE SİTE AVM K KONYA TR`) and the **amount** on the
  right (`2.951,97 TL`; the cents are printed smaller). The city and `TR` at the end are part of the
  merchant text: copy them.
- A **plus sign** (`+2.399,00 TL`, `+37.405,29 TL`) means money that came back (refund, or a
  payment of the card debt `Kredi Kartı Borç Ödeme`). Rows without a sign are purchases.
- The **installment marker** is the last line of the merchant text: `3/5 Taksit`, `2/3 Taksit`,
  `6/6 Taksit`. `Taksit - DALİİ OYUNCAK` at the start is part of the description. Return the marker
  (`3/5 Taksit`) as `installment_text`.
- Rows with the description `Altın Fırsatlar ...` and an amount of `0,00 TL` plus a small gold
  amount below it are gold-point notes: skip them. Gold points (`Altın Puan`) are never TL amounts.
- The block above the list (`Ekstre Toplamı`, `Son Ödeme Tarihi`, `Toplam Altın Puan`, month tabs,
  category percentages) is not a row.
- **POS slip** ("Müşteri Nüshası": `Tarih`, `Saat`, `Satış- Fiziki` or `Satış İade`, `Toplam
  Tutar`): ONE transaction. `merchant_raw` is the merchant line at the top, `amount_text` is the
  `Toplam Tutar`, `date_text` is `Tarih`, `time` is `Saat`. `Satış İade` is a refund: put a `+` in
  front of the amount (`+197,50 TL`); `Satış` is a purchase (no sign).
