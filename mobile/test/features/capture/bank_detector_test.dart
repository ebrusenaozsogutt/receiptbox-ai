import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/features/capture/domain/bank_detector.dart';
import 'package:receiptbox/features/capture/domain/bank_models.dart';

// The texts are short, made-up pieces of what the OCR gives for each bank's app (no real data).

const detector = BankDetector();

void main() {
  group('the three supported banks are recognised', () {
    final cases = <String, (String, BankKey)>{
      'Garanti: Bonus card and the app menu': (
        'BONUS DIJI\n[CARD]\nGerçekleşen Hareketler\nAna Sayfa  Hesap ve Kart  Başvurular  İşlemler',
        BankKey.garanti,
      ),
      'Garanti: slip with the logo': (
        'Dijital Slip\nTAKSİTLİ SATIŞ TUTARI\nGaranti BBVA',
        BankKey.garanti,
      ),
      'Garanti: card list title': (
        'BONUS BUSINESS TROY\nSon Dönem İçi Hareketleri',
        BankKey.garanti,
      ),
      'Kuveyt: logo with OCR slips': (
        'Yukarıda yazılı tutar\nKuUEYTTÜRK\nMüşteri Nüshası',
        BankKey.kuveyt,
      ),
      'Kuveyt: statement': (
        'Ekstre\nDöviz/Yatır...  Durumum  Para Trans...  Menü\n[BALANCE]',
        BankKey.kuveyt,
      ),
      'Kuveyt: period expenses': (
        'Dönem içi Harcamalar\nTümü  Asıl kart',
        BankKey.kuveyt,
      ),
      'Akbank: slip with the Axess logo': (
        'Dijital slip\nSATIŞ\naixess\nCHIP PARA',
        BankKey.akbank,
      ),
      'Akbank: card list': (
        'Kredi kartı\nChip-para ile öde  Erteleme İste\nAna sayfa  Transferler  Ödemeler  DijiOrtak',
        BankKey.akbank,
      ),
    };
    for (final entry in cases.entries) {
      test(entry.key, () {
        expect(detector.detect(entry.value.$1), entry.value.$2);
      });
    }
  });

  group('every other bank gets no hint', () {
    test('QNB (held out): ParaPuan and Hesap Kesim Tarihi', () {
      const text =
          'DÖNEM İÇİ HAREKETLER\nTL Hareketlerim  USD Hareketlerim\nAsil Kart- [CARD]\n0 ParaPuan\n[BALANCE]\nHesap Kesim Tarihi: 28.11.2026';
      expect(detector.detect(text), isNull);
    });

    test('Ziraat (held out): Kart Hareketleri', () {
      const text =
          'Kart Hareketleri\nToplam USD\nHarcama Tutarı\nÖdeme - Tesekkür Ederiz -';
      expect(detector.detect(text), isNull);
    });

    test('an empty or unrelated text', () {
      expect(detector.detect(''), isNull);
      expect(detector.detect('A101 MARKET\nTOPLAM 120,00'), isNull);
    });

    test('two banks with the same evidence tie: no guess', () {
      expect(detector.detect('Garanti\nKuveyt'), isNull);
    });
  });

  test('the key with the most evidence wins', () {
    expect(
      detector.detect('Garanti BBVA\nBONUS DIJI\nHesap ve Kart\nChip para'),
      BankKey.garanti,
    );
  });

  test('upper and lower case, with or without Turkish letters', () {
    expect(detector.detect('KUVEYT TÜRK'), BankKey.kuveyt);
    expect(detector.detect('kuveyt turk'), BankKey.kuveyt);
    expect(detector.detect('GARANTİ BBVA'), BankKey.garanti);
  });

  test('wire names are what the server expects', () {
    expect(BankKey.values.map((b) => b.wireName), [
      'garanti',
      'kuveyt',
      'akbank',
    ]);
  });
}
