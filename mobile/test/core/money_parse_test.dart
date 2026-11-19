import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/core/utils/money_format.dart';

void main() {
  group('parseMoneyToMinor', () {
    const good = {
      '494,60': 49460,
      '494.60': 49460,
      '1.349,90': 134990,
      '1,349.90': 134990,
      '1.349,90 TL': 134990,
      '₺270,30': 27030,
      '1349': 134900,
      '1.349': 134900, // a lone dot followed by 3 digits groups thousands
      '0,5': 50,
      '12,': 1200,
      ',50': 50,
      '  75  ': 7500,
    };
    for (final entry in good.entries) {
      test('"${entry.key}" is ${entry.value} kuruş', () {
        expect(parseMoneyToMinor(entry.key), entry.value);
      });
    }

    const bad = [
      '',
      'abc',
      '-5',
      '1,349', // ambiguous: refused
      '1,349,00',
      '12,345',
      '1,2,3',
      '10,999', // three decimals
      '1.2.3',
      '9999999999999', // too large
    ];
    for (final input in bad) {
      test('"$input" is refused', () {
        expect(parseMoneyToMinor(input), isNull);
      });
    }

    test('formatting and parsing agree', () {
      for (final minor in [0, 5, 99, 100, 27030, 134990, 123456789]) {
        expect(parseMoneyToMinor(formatMoneyMinor(minor)), minor);
      }
    });
  });
}
