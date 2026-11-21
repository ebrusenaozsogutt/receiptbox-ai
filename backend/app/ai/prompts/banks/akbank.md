## Bank hints: Akbank (Axess, Chip-para)

- **Card transaction list** ("Kredi kartı", tabs `Dönem içi`, `Bekleyen`, `Gelecek dönem`): each row
  is the **merchant** with the installment marker in parentheses at its end (`ZİRVE ANKARA GIDA TEM.
  (01/03)`, `FELDA IFFCO (04/04)`), the **amount** at the right (`10.695,96 TL`), and below it the
  **date** `20.11.2026`, followed by `- Taksit: 01/03` for installment rows. Rows on the `Bekleyen`
  tab are not booked yet: `is_pending` is true for them.
- **Signs are the other way round**: a purchase has NO sign (`10.695,96 TL`) and a payment or credit
  has a **minus** (`-10.000,00 TL`, `İNTERNET Şb-Ödemeniz için Te...`). Copy the sign as printed.
- `Chip-para ile öde` and `Erteleme İste` are buttons, not rows. `Chip-para`, `ParaPuan` amounts
  are points, never rows.
- The installment marker can stand twice (`(01/03)` in the name and `Taksit: 01/03` under it): return it
  once as `installment_text`.
- **Digital slip** ("Dijital slip", merchant block, `SATIŞ`, `Tutar :173,175.00 TL`, `Kart Taksit
  Tutar x Adet : 57.725,00 x 03`): ONE transaction. `merchant_raw` is the merchant name at the top,
  `amount_text` is the `Tutar` (the whole sale), `date_text` is the date next to `SATIŞ`
  (`19/11/2026`), `installment_text` is the number of installments after `x` (`03 TAKSİT`).
  `Yeni Bakiye` is a balance: ignore it.
