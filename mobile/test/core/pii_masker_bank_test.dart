import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/core/privacy/pii_masker.dart';

// Bank screenshot rules (P08, `bank: true`). Every name, number and amount below is made up.

const masker = PiiMasker();

String b(String text) => masker.mask(text, bank: true).text;
Map<PiiType, int> bc(String text) => masker.mask(text, bank: true).counts;
String m(String text) => masker.mask(text).text;

void main() {
  group('card holder name on a POS slip', () {
    test('after the hidden card number (Garanti layout)', () {
      const slip =
          'K.N: **** **** **** 3233\nAYSE ORNEK DEMIR\nTAKSITLI SATIS TUTARI 1.680,00 TL';
      expect(
        b(slip),
        'K.N: [CARD]\n[NAME]\nTAKSITLI SATIS TUTARI 1.680,00 TL',
      );
      expect(bc(slip), {PiiType.card: 1, PiiType.name: 1});
    });

    test('after "Satış" and before "Toplam Tutar" (Kuveyt layout)', () {
      const slip =
          'Terminal No: 12\nSatış İade\nAYSE ORNEK\n\nToplam Tutar\n197,50 TL';
      expect(b(slip), contains('[NAME]'));
      expect(b(slip), isNot(contains('AYSE')));
      expect(b(slip), contains('197,50 TL'));
    });

    test('a merchant name next to an amount is NOT a name', () {
      const list = 'Market -16,33 TL\nORNEK GIDA VE IHTIYAC\n(2/3)';
      expect(b(list), list);
    });

    test('the merchant at the top of a slip stays', () {
      const slip =
          'PAYCELL TRENDYOL ISTANBUL TR\nTarih: 07.09.2026\nToplam Tutar\n197,50 TL';
      expect(b(slip), slip);
    });

    test('not applied to receipts', () {
      const slip = 'Satış\nAYSE ORNEK\nToplam Tutar\n197,50 TL';
      expect(m(slip), slip);
    });
  });

  group('other party of a transfer', () {
    test('name before -FAST-', () {
      const line = '1415  Ahmet Ornek elektrik Sanayi-FAST-CEP SUBE-7807000244';
      expect(b(line), startsWith('[NAME] FAST-CEP SUBE'));
      expect(bc(line), {PiiType.name: 1});
    });

    test('a line without a transfer keyword is untouched', () {
      const line = 'ATM PARA CEKME-ATM Kodu:00887';
      expect(b(line), line);
    });
  });

  group('balances, totals and account numbers', () {
    final cases = <String, String>{
      'account header': '101- 69  -64.956,94 TL',
      'Ekstre Toplamı': 'Ekstre Toplamı  48.042,60 TL',
      'Ek Kart Toplamı': 'Ek Kart Toplamı  213.645,28 TL',
      'Ek Kart Toplamı with an OCR slip': 'Fk Kart Toplamı  213.645.28 TL',
      'Genel Toplam': 'Genel Toplam  772.390,54 TL',
      'Genel Toplam with an OCR slip': 'Gencl Toplam  772.390,54 TL',
      'Son Ödeme Tarihi': 'Son Ödeme Tarihi  12.10.2026',
      'Toplam Altın Puan': 'Toplam Altın Puan  200,00 TL',
      'Bakiye with an OCR slip': 'Yeni Bakipe  2,711.24',
    };
    for (final entry in cases.entries) {
      test(entry.key, () {
        expect(b(entry.value), '[BALANCE]');
        expect(bc(entry.value), {PiiType.balance: 1});
      });
    }

    test('"Bakiye" with an OCR slip is also hidden on a receipt', () {
      expect(m('Yeni Bakipe  2,711.24'), '[BALANCE]');
    });

    test('"Hes.No" number is hidden, the rest of the line stays', () {
      expect(b('Hes.No:99497881-970'), '[BALANCE]');
      expect(b('Tes.No:1091354797 ,TÜRKSAT'), '[BALANCE] ,TÜRKSAT');
    });

    test('a normal transaction row is untouched', () {
      const row = '20.07.2026  1.600,00 TL\nKONYA DANS VE SANAT 3/5 Taksit';
      expect(b(row), row);
    });

    test('"Genel Toplam" stays on a receipt (bank: false)', () {
      expect(m('GENEL TOPLAM  270,30'), 'GENEL TOPLAM  270,30');
    });
  });

  group('partly hidden cards', () {
    final cases = <String, String>{
      'first four and stars': 'Asıl Kart- 9792 ******',
      'first four, stars, last four': 'ATM PARA CEKME-5170*******3717-ATM',
      'garbled stars': 'Ek Kart- 9792 *ka',
    };
    for (final entry in cases.entries) {
      test(entry.key, () {
        expect(b(entry.value), contains('[CARD]'));
        expect(b(entry.value), isNot(contains('9792')));
        expect(b(entry.value), isNot(contains('5170')));
      });
    }

    test('a fully starred card is masked as before', () {
      expect(b('K.N: **** **** **** 3233'), 'K.N: [CARD]');
    });
  });

  test('a transaction list passes unchanged', () {
    const list =
        '12 Market -16.128,33 TL\nKas\n2026 ORNEK GIDA (2/3)\n'
        '6 Kart Ödemesi +160.855,99 TL\nCep Şube Ödeme';
    expect(b(list), list);
  });
}
