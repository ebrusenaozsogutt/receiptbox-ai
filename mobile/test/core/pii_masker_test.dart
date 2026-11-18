import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/core/privacy/pii_masker.dart';

// All numbers below are made up or well-known public TEST numbers (e.g. the Visa test card
// 4111 1111 1111 1111, the sample IBAN TR33 0006 1005 1978 6457 8413 26). No real data.

const masker = PiiMasker();

String m(String text) => masker.mask(text).text;
Map<PiiType, int> c(String text) => masker.mask(text).counts;

/// Builds a VALID TCKN from its first nine digits (same rule as the official algorithm), so
/// the test data can not contain a typo.
String tckn(String first9) {
  final d = first9.codeUnits.map((u) => u - 0x30).toList();
  final tenth =
      (((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) %
              10 +
          10) %
      10;
  final all = [...d, tenth];
  final eleventh = all.fold(0, (sum, digit) => sum + digit) % 10;
  return '${all.join()}$eleventh';
}

void main() {
  group('IBAN', () {
    const iban = 'TR33 0006 1005 1978 6457 8413 26';
    final cases = <String, String>{
      'spaced': iban,
      'compact': 'TR330006100519786457841326',
      'lower case (OCR)': 'tr33 0006 1005 1978 6457 8413 26',
      'partly hidden': 'TR33 0006 **** **** **** 8413 26',
      'one digit lost by OCR': 'TR33 0006 1005 1978 6457 8413 2',
      'non-breaking spaces': 'TR33 0006 1005 1978 6457 8413 26',
    };
    for (final entry in cases.entries) {
      test(entry.key, () {
        expect(m(entry.value), '[IBAN]');
        expect(c(entry.value), {PiiType.iban: 1});
      });
    }

    test('inside a Turkish sentence', () {
      expect(
        m('Alıcı IBAN: $iban Ziraat Bankası'),
        'Alıcı IBAN: [IBAN] Ziraat Bankası',
      );
    });

    test('the next line is not swallowed', () {
      expect(m('$iban\nTutar: 1.500,00 TL'), '[IBAN]\nTutar: 1.500,00 TL');
    });

    test('a too short "TR12 3456" is left alone', () {
      expect(m('TR12 3456'), 'TR12 3456');
    });

    test('words that merely start with TR are left alone', () {
      expect(m('TRENDYOL 2/6 412,50 TL'), 'TRENDYOL 2/6 412,50 TL');
    });
  });

  group('card numbers', () {
    final valid = <String, String>{
      'Visa spaced': '4111 1111 1111 1111',
      'Visa compact': '4111111111111111',
      'Visa dashes': '4111-1111-1111-1111',
      'Mastercard': '5555 5555 5555 4444',
      'Amex 4-6-5': '3782 822463 10005',
      'Diners (14 digits)': '3056 9309 0259 04',
      'Discover': '6011 1111 1111 1117',
    };
    for (final entry in valid.entries) {
      test('${entry.key}: ${entry.value}', () {
        expect(m(entry.value), '[CARD]');
        expect(c(entry.value), {PiiType.card: 1});
      });
    }

    final hidden = <String, String>{
      'middle stars': '4543 **** **** 1234',
      'part of the middle hidden': '4543 12** **** 1234',
      'only last four': '**** **** **** 1234',
      'x as mask': '4543 xxxx xxxx 1234',
      'bullets': '4543 •••• •••• 1234',
    };
    for (final entry in hidden.entries) {
      test('partly hidden, ${entry.key}', () {
        expect(m(entry.value), '[CARD]');
      });
    }

    test('in a Turkish sentence', () {
      expect(
        m('Kart No: 4111 1111 1111 1111 ile ödendi'),
        'Kart No: [CARD] ile ödendi',
      );
    });

    test('16 digits that fail the Luhn check are not a card', () {
      expect(m('4111 1111 1111 1112'), '4111 1111 1111 1112');
    });

    test(
      'a long number with letters (like an e-invoice number) is left alone',
      () {
        expect(m('ABC2024000000123'), 'ABC2024000000123');
      },
    );
  });

  group('TCKN', () {
    test('valid number with a label', () {
      expect(m('TCKN: ${tckn('123456789')}'), 'TCKN: [TCKN]');
      expect(c('TCKN: ${tckn('123456789')}'), {PiiType.tckn: 1});
    });

    test('known valid examples', () {
      expect(m('10000000146'), '[TCKN]');
      expect(m('11111111110'), '[TCKN]');
    });

    test('the generator itself produces numbers the rule accepts', () {
      for (final prefix in ['987654321', '555555555', '246813579']) {
        expect(m(tckn(prefix)), '[TCKN]', reason: prefix);
      }
    });

    test('inside a Turkish sentence', () {
      final id = tckn('223344556');
      expect(
        m('T.C. Kimlik No: $id olan hesap'),
        'T.C. Kimlik No: [TCKN] olan hesap',
      );
    });

    test('11 digits that fail the checksum are NOT masked', () {
      expect(m('12345678901'), '12345678901');
      expect(m('99999999999'), '99999999999');
    });

    test('a number starting with 0 is never a TCKN', () {
      expect(m('01234567890'), '01234567890');
      expect(m('00000000000'), '00000000000');
    });

    test('10- and 12-digit numbers are not TCKNs', () {
      expect(m('1000000014'), '1000000014');
      expect(m('100000001462'), '100000001462');
    });
  });

  group('phone numbers', () {
    final phones = <String, String>{
      'local mobile': '0532 123 45 67',
      'compact': '05321234567',
      'with +90': '+90 532 123 45 67',
      'compact +90': '+905321234567',
      'with 0090': '0090 532 123 45 67',
      'brackets': '(0532) 123 45 67',
      'zero and brackets': '0 (532) 123 45 67',
      'dashes': '0532-123-45-67',
      'without the leading zero': '532 123 45 67',
      'landline Istanbul': '0212 555 12 34',
      'landline spaced': '0 212 555 12 34',
      'landline +90 brackets': '+90 (212) 555 12 34',
    };
    for (final entry in phones.entries) {
      test('${entry.key}: ${entry.value}', () {
        expect(m(entry.value), '[PHONE]');
        expect(c(entry.value), {PiiType.phone: 1});
      });
    }

    test('with a label', () {
      expect(m('Tel: 0532 123 45 67'), 'Tel: [PHONE]');
    });

    test('a seller VKN (10 digits) after its label is NOT a phone number', () {
      expect(m('VKN: 5330012345'), 'VKN: 5330012345');
      expect(m('Vergi No: 5330012345'), 'Vergi No: 5330012345');
      expect(m('V.D. 5330012345'), 'V.D. 5330012345');
    });

    test('totals, dates and times are not phone numbers', () {
      for (final text in [
        'TOPLAM *494,60',
        '1.349,90 TL',
        '09.11.2026 18:27',
        '2026-11-09 18:27:33',
        'KDV %20 82,43',
        'FİŞ NO: 0042',
      ]) {
        expect(m(text), text, reason: text);
      }
    });
  });

  group('e-mail', () {
    test('simple', () => expect(m('ebru@example.com'), '[EMAIL]'));
    test('with a label, plus tag and subdomain', () {
      expect(m('Mail: ebru.yilmaz+fis@sub.example.co.uk'), 'Mail: [EMAIL]');
    });
    test('digits in the address do not turn it into a phone number', () {
      expect(c('5321234567@mail.com'), {PiiType.email: 1});
    });
    test('an @ without a domain is left alone', () {
      expect(m('@ebru'), '@ebru');
      expect(m('a@b'), 'a@b');
    });
  });

  group('balance / limit / account lines (whole line replaced)', () {
    final lines = <String, String>{
      'Kullanılabilir Bakiye: 12.450,00 TL': '[BALANCE]',
      'KULLANILABİLİR LİMİT 5.000,00 TL': '[BALANCE]',
      'Kullanilabilir bakiye 12.450,00': '[BALANCE]', // OCR dropped the dots
      'Toplam Borç: 3.200,00 TL': '[BALANCE]',
      'TOPLAM BORÇ 3.200,00': '[BALANCE]',
      'Hesap No: 12345678': '[BALANCE]',
      'Hesap Numarası 12345678': '[BALANCE]',
      'Limit: 10.000 TL': '[BALANCE]',
      'Bakiyeniz 250,00 TL': '[BALANCE]',
      'Güncel Bakiye 99,00': '[BALANCE]',
    };
    for (final entry in lines.entries) {
      test(entry.key, () => expect(m(entry.key), entry.value));
    }

    test('only that line goes, the rows around it stay', () {
      expect(
        m(
          'Kullanılabilir Bakiye: 12.450,00 TL\nTRENDYOL 2/6   412,50 TL\nMIGROS   494,60 TL',
        ),
        '[BALANCE]\nTRENDYOL 2/6   412,50 TL\nMIGROS   494,60 TL',
      );
    });

    test('company names like "LIMITED" and ordinary totals are left alone', () {
      expect(m('ABC TEKSTIL LIMITED'), 'ABC TEKSTIL LIMITED');
      expect(m('TOPLAM: 494,60'), 'TOPLAM: 494,60');
    });
  });

  group('names', () {
    test('after "Sayın" on the same line', () {
      expect(m('Sayın Ebru Yılmaz'), 'Sayın [NAME]');
    });
    test('"Ad Soyad:" keeps the colon', () {
      expect(m('Ad Soyad: Ebru Yılmaz'), 'Ad Soyad: [NAME]');
    });
    test('"Adı Soyadı"', () {
      expect(m('Adı Soyadı: Ayşe Kaya'), 'Adı Soyadı: [NAME]');
    });
    test('"Kart Sahibi: ..."', () {
      expect(m('Kart Sahibi: EBRU YILMAZ'), 'Kart Sahibi: [NAME]');
    });
    test('"Müşteri: ..."', () {
      expect(m('Müşteri: Ahmet Demir'), 'Müşteri: [NAME]');
    });
    test('the name on the NEXT line', () {
      expect(
        m('KART SAHİBİ\nEBRU YILMAZ\nTutar 100,00'),
        'KART SAHİBİ\n[NAME]\nTutar 100,00',
      );
    });
    test('OCR without Turkish letters', () {
      expect(m('Sayin Ayse Kaya'), 'Sayin [NAME]');
    });
    test('counts one name', () {
      expect(c('Sayın Ebru Yılmaz'), {PiiType.name: 1});
    });
    test('"MÜŞTERİ NÜSHASI" and similar phrases are not names', () {
      for (final text in [
        'MÜŞTERİ NÜSHASI',
        'Müşteri Kopyası',
        'MÜŞTERİ HİZMETLERİ',
        'Müşteri Temsilcisi',
      ]) {
        expect(m(text), text, reason: text);
      }
    });
  });

  group('several kinds in one text', () {
    test('counts per type', () {
      final result = masker.mask(
        'Sayın Ebru Yılmaz\n'
        'ebru@example.com\n'
        'Tel: 0532 123 45 67\n'
        'IBAN: TR33 0006 1005 1978 6457 8413 26\n'
        'Kart: 4111 1111 1111 1111\n'
        'TCKN: ${tckn('123456789')}\n'
        'Kullanılabilir Bakiye: 1.000,00 TL',
      );

      expect(result.counts, {
        PiiType.name: 1,
        PiiType.email: 1,
        PiiType.phone: 1,
        PiiType.iban: 1,
        PiiType.card: 1,
        PiiType.tckn: 1,
        PiiType.balance: 1,
      });
      expect(result.total, 7);
      expect(result.text, contains('[NAME]'));
      expect(result.text, isNot(contains('ebru')));
      expect(result.text, isNot(contains('4111')));
      expect(result.text, isNot(contains('0006')));
    });

    test('masking twice changes nothing more', () {
      const text =
          'Sayın Ebru\nTel 0532 123 45 67\nTR33 0006 1005 1978 6457 8413 26';
      expect(m(m(text)), m(text));
    });
  });

  group('receipts and bank screenshots stay readable', () {
    test('a market receipt is unchanged (totals, dates, VKN, items)', () {
      const receipt =
          'MIGROS TICARET A.S.\n'
          'VKN: 5330012345\n'
          'FIS NO: 0042\n'
          '09.11.2026 18:27\n'
          'SUT 1L          69,90\n'
          "YUMURTA 15'LI  139,90\n"
          'KAHVE 250GR    249,90\n'
          'TOPLAM         *494,60\n'
          'KREDI KARTI    *494,60\n'
          'KDV %10 44,96';

      final result = masker.mask(receipt);

      expect(result.text, receipt);
      expect(result.counts, isEmpty);
    });

    test('a POS slip with installments is unchanged', () {
      const slip =
          'TAKSIT SAYISI: 6\n'
          'AYLIK TUTAR: 2.083,17\n'
          'TOPLAM: 12.499,00\n'
          'ONAY KODU: 123456\n'
          'TARIH: 09/11/2026 18:27';
      expect(m(slip), slip);
    });

    test(
      'a bank screenshot loses balance, account and name but keeps the rows',
      () {
        final masked = m(
          'Sayın Ebru Yılmaz\n'
          'Hesap No: 1234567\n'
          'Kullanılabilir Bakiye: 12.450,00 TL\n'
          'Bugün\n'
          'TRENDYOL 2/6      -412,50 TL\n'
          'Dün\n'
          'MIGROS            -494,60 TL',
        );

        expect(
          masked,
          'Sayın [NAME]\n'
          '[BALANCE]\n'
          '[BALANCE]\n'
          'Bugün\n'
          'TRENDYOL 2/6      -412,50 TL\n'
          'Dün\n'
          'MIGROS            -494,60 TL',
        );
      },
    );

    test('an e-invoice line with an ETTN is left alone', () {
      const text = 'ETTN: 3f2b8c1e-5d4a-4b7e-9c11-0a1b2c3d4e5f';
      expect(m(text), text);
    });
  });

  group('edge cases', () {
    test('empty text', () => expect(m(''), ''));
    test('only whitespace', () => expect(m('  \n  '), '  \n  '));
    test('Windows line endings become \\n', () {
      expect(m('Sayın Ebru\r\nTOPLAM 10,00'), 'Sayın [NAME]\nTOPLAM 10,00');
    });
    test('the result has no way back to the original (counts only)', () {
      final result = masker.mask('ebru@example.com');
      expect(result.counts.keys, [PiiType.email]);
      expect(result.text, isNot(contains('@')));
    });
  });

  group('foldForMatching', () {
    test('keeps the length and drops Turkish letters', () {
      const input = 'İĞÜŞÖÇıiI';
      final folded = PiiMasker.foldForMatching(input);

      expect(folded.length, input.length);
      expect(
        folded,
        'igusocii'
        'i',
      );
    });
  });
}
