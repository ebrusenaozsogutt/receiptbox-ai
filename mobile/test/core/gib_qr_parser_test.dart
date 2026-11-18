import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/core/ocr/gib_qr_parser.dart';

// Every value below is made up (fake tax numbers, fake buyer TCKN, fake ETTN).

const parser = GibQrParser();

const _earchive = '''
{"vkntckn":"1234567890","avkntckn":"10000000146","senaryo":"EARSIVFATURA","tip":"SATIS",
"tarih":"2026-11-09","no":"ABC2026000000123","ettn":"3f2b8c1e-5d4a-4b7e-9c11-0a1b2c3d4e5f",
"parabirimi":"TRY","malhizmettoplam":"411.33","kdvmatrah(20)":"411.33","hesaplanankdv(20)":"82.27",
"vergidahil":"493.60","odenecek":"493.60"}
''';

void main() {
  group('a GİB invoice QR is recognised', () {
    test('e-Archive invoice', () {
      final payload = parser.parse(_earchive);

      expect(payload, isNotNull);
      expect(payload!['ettn'], '3f2b8c1e-5d4a-4b7e-9c11-0a1b2c3d4e5f');
      expect(payload['odenecek'], '493.60');
      expect(payload['tarih'], '2026-11-09');
      expect(payload['vkntckn'], '1234567890'); // the SELLER's number is kept
    });

    test('any one of ettn / odenecek / vergidahil is enough', () {
      for (final key in ['ettn', 'odenecek', 'vergidahil']) {
        expect(parser.parse('{"$key":"1"}'), isNotNull, reason: key);
      }
    });

    test(
      'numbers with a comma are kept as written (the backend parses them)',
      () {
        final payload = parser.parse(
          '{"odenecek":"1.349,90","vergidahil":"1349,90"}',
        );

        expect(payload!['odenecek'], '1.349,90');
      },
    );

    test('numbers that are JSON numbers work too', () {
      final payload = parser.parse('{"ettn":"x","odenecek":493.6}');

      expect(payload!['odenecek'], 493.6);
    });

    test('unknown keys are ignored (kept, never an error)', () {
      final payload = parser.parse(
        '{"odenecek":"1","yenialan":"x","baska":{"a":1}}',
      );

      expect(payload, containsPair('yenialan', 'x'));
    });

    test('whitespace and a BOM around the JSON do not matter', () {
      expect(parser.parse('﻿  \n{"odenecek":"1"}\n  '), isNotNull);
    });

    test('keys are matched case-insensitively', () {
      expect(parser.parse('{"ODENECEK":"1","ETTN":"x"}'), isNotNull);
    });
  });

  group('the buyer identity (avkntckn) never comes out', () {
    test('it is removed from the payload', () {
      final payload = parser.parse(_earchive)!;

      expect(payload.containsKey('avkntckn'), isFalse);
    });

    test('and from anything made of the payload', () {
      final payload = parser.parse(_earchive)!;

      expect(jsonEncode(payload), isNot(contains('avkntckn')));
      expect(jsonEncode(payload), isNot(contains('10000000146')));
      expect(payload.toString(), isNot(contains('10000000146')));
    });

    test('whatever the letter case of the key', () {
      for (final key in ['AVKNTCKN', 'Avkntckn', 'aVkNtCkN']) {
        final payload = parser.parse('{"odenecek":"1","$key":"10000000146"}')!;
        expect(
          payload.keys.map((k) => k.toLowerCase()),
          isNot(contains('avkntckn')),
        );
        expect(payload.values, isNot(contains('10000000146')), reason: key);
      }
    });

    test('a payload that is ONLY the marker plus avkntckn still works', () {
      final payload = parser.parse(
        '{"odenecek":"5","avkntckn":"10000000146"}',
      )!;

      expect(payload, {'odenecek': '5'});
    });
  });

  group('everything else is NOT a GİB QR', () {
    final others = <String, String>{
      'empty': '',
      'spaces': '   ',
      'a web address': 'https://example.com/fatura?id=1',
      'a payment string': '00020101021226580014TR.GOV.PAY',
      'a product barcode': '8690504123456',
      'broken JSON': '{"ettn": "x", ',
      'a JSON list': '[{"ettn":"x"}]',
      'a JSON string': '"ettn"',
      'JSON without a marker key': '{"vkntckn":"1","tarih":"2026-11-09"}',
      'plain text': 'odenecek 493,60',
    };
    for (final entry in others.entries) {
      test(entry.key, () => expect(parser.parse(entry.value), isNull));
    }
  });

  group('firstGibPayload (several QR codes in one image)', () {
    test('skips other codes and returns the invoice', () {
      final payload = parser.firstGibPayload([
        'https://example.com',
        '8690504123456',
        _earchive,
      ]);

      expect(payload!['odenecek'], '493.60');
      expect(payload.containsKey('avkntckn'), isFalse);
    });

    test('null when there is none', () {
      expect(parser.firstGibPayload(['https://example.com']), isNull);
      expect(parser.firstGibPayload([]), isNull);
    });
  });
}
