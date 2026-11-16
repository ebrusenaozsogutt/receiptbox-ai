import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/core/utils/date_format.dart';
import 'package:receiptbox/core/utils/money_format.dart';
import 'package:receiptbox/core/widgets/date_text.dart';
import 'package:receiptbox/core/widgets/money_text.dart';

void main() {
  setUpAll(() => initializeDateFormatting('tr_TR'));

  group('formatMoneyTl (minor units -> "1.349,90 TL")', () {
    const cases = <int, String>{
      134990: '1.349,90 TL',
      49460: '494,60 TL',
      0: '0,00 TL',
      5: '0,05 TL',
      99: '0,99 TL',
      100: '1,00 TL',
      100000: '1.000,00 TL',
      134900000: '1.349.000,00 TL',
      99999999999: '999.999.999,99 TL',
      -250: '-2,50 TL',
      -134990: '-1.349,90 TL',
    };
    for (final entry in cases.entries) {
      test('${entry.key} -> ${entry.value}', () {
        expect(formatMoneyTl(entry.key), entry.value);
      });
    }

    test('without the currency sign', () {
      expect(formatMoneyMinor(134990), '1.349,90');
    });
  });

  group('MoneyText', () {
    testWidgets('shows the amount as Turkish text', (tester) async {
      await tester.pumpWidget(
        const Directionality(
          textDirection: TextDirection.ltr,
          child: MoneyText(134990),
        ),
      );

      expect(find.text('1.349,90 TL'), findsOneWidget);
    });

    testWidgets('uses the given style', (tester) async {
      const style = TextStyle(fontSize: 11);
      await tester.pumpWidget(
        const Directionality(
          textDirection: TextDirection.ltr,
          child: MoneyText(49460, style: style),
        ),
      );

      expect(tester.widget<Text>(find.text('494,60 TL')).style, style);
    });
  });

  group('formatDateTr / DateText (09 Kasım 2026)', () {
    final cases = <DateTime, String>{
      DateTime(2026, 11, 9): '09 Kasım 2026',
      DateTime(2027, 1, 1): '01 Ocak 2027',
      DateTime(2026, 12, 31): '31 Aralık 2026',
      DateTime(2026, 2, 28): '28 Şubat 2026',
      DateTime(2026, 8, 30): '30 Ağustos 2026',
      DateTime(2026, 10, 5): '05 Ekim 2026',
    };
    for (final entry in cases.entries) {
      test(
        '${entry.key.toIso8601String().substring(0, 10)} -> ${entry.value}',
        () {
          expect(formatDateTr(entry.key), entry.value);
        },
      );
    }

    testWidgets('DateText shows the date', (tester) async {
      await tester.pumpWidget(
        Directionality(
          textDirection: TextDirection.ltr,
          child: DateText(DateTime(2026, 11, 9)),
        ),
      );

      expect(find.text('09 Kasım 2026'), findsOneWidget);
    });
  });

  group('widgets share one look', () {
    testWidgets('MoneyText works inside a MaterialApp', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: Scaffold(body: MoneyText(100000))),
      );

      expect(find.text('1.000,00 TL'), findsOneWidget);
    });
  });
}
