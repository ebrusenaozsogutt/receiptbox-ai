**Tablo E3-1. Asistan değerlendirmesi.** Model: gemini-3.5-flash-lite (ücretsiz plan), tohumlanmış değerlendirme veritabanı, bugün = 26.11.2026; altın cevaplar uygulamadan bağımsız SQL ile hesaplandı. Köşeli parantez: %95 bootstrap güven aralığı. **Ara sonuç: 40/88 soru** (ücretsiz kotanın günlük sınırı; kalan sorular sonraki günlerde aynı önbellekle tamamlanır).

| Ölçüt | n | Değer [%95 GA] |
|---|---:|---|
| Araç seçimi doğruluğu | 40 | %100,0 [%100,0 – %100,0] |
| Cevap doğruluğu (tüm sorular) | 40 | %95,0 [%87,5 – %100,0] |
| Sayısal doğruluk (sayı içeren altın cevaplar) | 38 | %94,7 [%86,8 – %100,0] |
| Doğru 'kayıt yok' cevabı | 2 | %100,0 [%100,0 – %100,0] |
| Kapsam dışı soruyu doğru geri çevirme | 0 | (henüz soru yok) |
| Halüsinasyon: modelin İLK cevabında araçta olmayan sayı | 40 | %0,0 [%0,0 – %0,0] |
| Son cevapta araçta olmayan sayı | 40 | %0,0 [%0,0 – %0,0] |
| Cevap süresi (canlı istekler) | 40 | medyan 2,4 sn, p95 3,1 sn |

**Tablo E3-2. Soru gruplarına göre sonuç.**

| Grup | n | Doğru araç | Doğru cevap |
|---|---:|---:|---:|
| Kategori + dönem | 16 | 16 | 15 |
| Karşılaştırma | 2 | 2 | 2 |
| Tek mağaza | 12 | 12 | 11 |
| Göreli dönem (geçen yıl, son 3 ay) | 10 | 10 | 10 |

**Tablo E3-3. Yanlış cevaplar (hata analizi).**

| Soru | Çağrılan araç ve argümanlar | Cevap |
|---|---|---|
| Geçen ay akaryakıta ne kadar harcadım? | aggregate_spending `[{"date_to": "2025-10-31", "date_from": "2025-10-01", "category": "FUEL"}]` | Geçen ay akaryakıta toplam 3.806,39 TL harcadın. |
| Geçen ay A101'de ne kadar harcadım? | aggregate_spending `[{"date_to": "2025-10-31", "merchant": "A101", "date_from": "2025-10-01"}]` | Geçen ay A101'de toplam 733,72 TL harcadın. |
