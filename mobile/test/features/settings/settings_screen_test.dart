import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../../support/fakes.dart';

Future<TestApp> _openSettings(WidgetTester tester, {TestApp? app}) async {
  final testApp = app ?? await TestApp.signedIn();
  await tester.pumpWidget(testApp.app());
  await tester.pumpAndSettle();
  await tester.tap(find.byTooltip('Ayarlar'));
  await tester.pumpAndSettle();
  return testApp;
}

Switch _receiptSwitch(WidgetTester tester) =>
    tester.widget<Switch>(find.byType(Switch));

void main() {
  testWidgets('shows the account e-mail and the sections', (tester) async {
    await _openSettings(tester);

    expect(find.text('ebru@example.com'), findsOneWidget);
    expect(find.text('HESAP'), findsOneWidget);
    expect(find.text('GİZLİLİK'), findsOneWidget);
    expect(find.text('BAĞLANTI'), findsOneWidget);
    expect(find.text('Çıkış yap'), findsOneWidget);
    expect(find.text('Hesabı sil'), findsOneWidget);
  });

  group('"Fiş görsellerini sakla"', () {
    testWidgets('is ON by default (receipt photos are warranty proof)', (
      tester,
    ) async {
      await _openSettings(tester);

      expect(find.text('Fiş görsellerini sakla'), findsOneWidget);
      expect(_receiptSwitch(tester).value, isTrue);
    });

    testWidgets('says that bank screenshots are never stored', (tester) async {
      await _openSettings(tester);

      expect(
        find.textContaining('Banka ekran görüntüleri hiçbir zaman saklanmaz'),
        findsOneWidget,
      );
    });

    testWidgets('turning it off is saved on the device', (tester) async {
      final app = await _openSettings(tester);

      await tester.tap(find.byType(Switch));
      await tester.pumpAndSettle();

      expect(_receiptSwitch(tester).value, isFalse);
      expect(app.preferences.getBool('keep_receipt_images'), isFalse);
    });

    testWidgets('the choice survives a restart', (tester) async {
      final app = await _openSettings(tester);
      await tester.tap(find.byType(Switch));
      await tester.pumpAndSettle();

      await tester.pumpWidget(const SizedBox()); // kill the app
      await _openSettings(tester, app: app); // start it again

      expect(_receiptSwitch(tester).value, isFalse);
    });

    testWidgets('can be turned back on', (tester) async {
      final app = await _openSettings(tester);
      await tester.tap(find.byType(Switch));
      await tester.pumpAndSettle();

      await tester.tap(find.byType(Switch));
      await tester.pumpAndSettle();

      expect(_receiptSwitch(tester).value, isTrue);
      expect(app.preferences.getBool('keep_receipt_images'), isTrue);
    });
  });

  testWidgets('shows the server status row', (tester) async {
    await _openSettings(tester);

    expect(find.text('Sunucu: bağlı'), findsOneWidget);
  });

  testWidgets('the back arrow returns to Home', (tester) async {
    await _openSettings(tester);

    await tester.tap(find.byType(BackButton));
    await tester.pumpAndSettle();

    expect(find.text('Henüz harcama yok'), findsOneWidget);
  });
}
