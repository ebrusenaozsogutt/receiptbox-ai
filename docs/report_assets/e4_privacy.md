**Tablo E4-1. Kişisel veri maskeleme başarısı (recall), türe göre.** 600 sentetik fiş / banka metni, 1782 kişisel değer; maskeleyici: uygulamanın kendi Dart kodu (cihazda çalışan). Köşeli parantez: %95 bootstrap güven aralığı.

| Tür | n | Maskelenen | Recall [%95 GA] |
|---|---:|---:|---|
| İsim (anahtar kelimeli) | 204 | 204 | %100,0 [%100,0 – %100,0] |
| İsim (anahtar kelimesiz) | 189 | 0 | %0,0 [%0,0 – %0,0] |
| IBAN | 185 | 169 | %91,4 [%87,0 – %95,1] |
| Kart numarası | 203 | 186 | %91,6 [%87,7 – %95,1] |
| Kısmen maskeli kart | 200 | 200 | %100,0 [%100,0 – %100,0] |
| TCKN | 208 | 174 | %83,7 [%78,8 – %88,5] |
| Telefon | 191 | 167 | %87,4 [%82,7 – %91,6] |
| E-posta | 203 | 203 | %100,0 [%100,0 – %100,0] |
| Bakiye / limit / hesap satırı | 199 | 199 | %100,0 [%100,0 – %100,0] |
| **Tümü** | 1782 | | %84,3 [%82,6 – %85,9] |
| Tümü, anahtar kelimesiz isimler hariç | | | %94,3 [%93,1 – %95,4] |

**Tablo E4-2. Kişisel olmayan benzer değerlerde yanlış maskeleme oranı.** 2376 değer.

| Tür | n | Yanlışlıkla maskelenen | Yanlış pozitif oranı [%95 GA] |
|---|---:|---:|---|
| Toplam tutar | 291 | 0 | %0,0 [%0,0 – %0,0] |
| Tarih | 294 | 0 | %0,0 [%0,0 – %0,0] |
| Saat | 285 | 0 | %0,0 [%0,0 – %0,0] |
| 11 hane, geçersiz TCKN | 314 | 0 | %0,0 [%0,0 – %0,0] |
| 16 hane, Luhn'dan geçmeyen | 300 | 0 | %0,0 [%0,0 – %0,0] |
| EAN-13 barkod | 283 | 20 | %7,1 [%4,2 – %10,2] |
| 10 haneli vergi no (VKN) | 310 | 0 | %0,0 [%0,0 – %0,0] |
| Fiş / Z numarası | 299 | 0 | %0,0 [%0,0 – %0,0] |
| **Tümü** | 2376 | | %0,8 [%0,5 – %1,2] |

**Tablo E4-3. OCR hatası olan ve olmayan değerlerde maskeleme başarısı.** OCR hatası: 0 yerine O, rakam grubunun içinde fazladan boşluk ya da ayraçların kaybolması (değerlerin %20'si).

| Tür | Değer | n | Recall [%95 GA] |
|---|---|---:|---|
| IBAN | temiz | 137 | %100,0 [%100,0 – %100,0] |
| IBAN | OCR hatalı | 48 | %66,7 [%52,1 – %79,2] |
| Kart numarası | temiz | 159 | %100,0 [%100,0 – %100,0] |
| Kart numarası | OCR hatalı | 44 | %61,4 [%45,5 – %75,0] |
| TCKN | temiz | 173 | %100,0 [%100,0 – %100,0] |
| TCKN | OCR hatalı | 35 | %2,9 [%0,0 – %8,6] |
| Telefon | temiz | 144 | %100,0 [%100,0 – %100,0] |
| Telefon | OCR hatalı | 47 | %48,9 [%34,0 – %63,8] |

Not: Metinler sentetiktir ve değer biçimleri maskeleyicinin kurallarını bilen biri tarafından üretilmiştir; temiz değerlerde %100'e yakın sonuçlar bu yüzden iyimserdir. OCR hatalı satırlar gerçek hayattaki zayıflığı gösterir. Anahtar kelimesiz isimler (ör. 'Kasiyer: …') tasarım gereği maskelenmez (spec 15.1: isimler yalnızca 'Sayın', 'Ad Soyad', 'Kart Sahibi', 'Müşteri' sonrasında).
