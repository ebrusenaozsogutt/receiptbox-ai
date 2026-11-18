import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/features/shell/presentation/add_sheet.dart';

import '../../support/fakes.dart';

Future<void> _openSignedInApp(WidgetTester tester) async {
  final app = await TestApp.signedIn();
  await tester.pumpWidget(app.app());
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows the five bottom navigation items in the designed order', (
    tester,
  ) async {
    await _openSignedInApp(tester);

    for (final label in ['Ana Sayfa', 'Harcamalar', 'Ürünler', 'Asistan']) {
      expect(find.text(label), findsWidgets, reason: label);
    }
    expect(find.byKey(const Key('nav_add_button')), findsOneWidget);

    final x = {
      'Harcamalar': tester.getCenter(find.text('Harcamalar').last).dx,
      'Ürünler': tester.getCenter(find.text('Ürünler').last).dx,
      'Asistan': tester.getCenter(find.text('Asistan').last).dx,
      '+': tester.getCenter(find.byKey(const Key('nav_add_button'))).dx,
    };
    expect(x['Harcamalar']!, lessThan(x['+']!));
    expect(x['+']!, lessThan(x['Ürünler']!));
    expect(x['Ürünler']!, lessThan(x['Asistan']!));
  });

  group('every tab opens its own screen', () {
    final tabs = {
      'Harcamalar': 'Harcamaların burada listelenecek',
      'Ürünler': 'Ürünlerin burada olacak',
      'Asistan': 'Asistan yakında burada',
    };
    for (final tab in tabs.entries) {
      testWidgets('${tab.key} -> "${tab.value}"', (tester) async {
        await _openSignedInApp(tester);

        await tester.tap(find.text(tab.key).last);
        await tester.pumpAndSettle();

        expect(find.text(tab.value), findsOneWidget);
      });
    }

    testWidgets('and "Ana Sayfa" goes back to Home', (tester) async {
      await _openSignedInApp(tester);
      await tester.tap(find.text('Asistan').last);
      await tester.pumpAndSettle();

      await tester.tap(find.text('Ana Sayfa').last);
      await tester.pumpAndSettle();

      expect(find.text('Henüz harcama yok'), findsOneWidget);
    });

    testWidgets('each tab keeps its place when switching back and forth', (
      tester,
    ) async {
      await _openSignedInApp(tester);
      await tester.tap(find.text('Ürünler').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Harcamalar').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Ürünler').last);
      await tester.pumpAndSettle();

      expect(find.text('Ürünlerin burada olacak'), findsOneWidget);
    });
  });

  group('the (+) button', () {
    testWidgets('opens a sheet with the 5 actions of spec 17', (tester) async {
      await _openSignedInApp(tester);

      await tester.tap(find.byKey(const Key('nav_add_button')));
      await tester.pumpAndSettle();

      for (final title in [
        'Fiş Tara',
        'Galeriden Ekle',
        'Banka Ekran Görüntüsü',
        'Manuel Harcama',
        'Ürün Ekle',
      ]) {
        expect(find.text(title), findsOneWidget, reason: title);
      }
      expect(addActions, hasLength(5));
    });

    for (final action in addActions) {
      testWidgets('"${action.title}" opens its screen and back returns', (
        tester,
      ) async {
        await _openSignedInApp(tester);
        await tester.tap(find.byKey(const Key('nav_add_button')));
        await tester.pumpAndSettle();

        await tester.tap(find.byKey(Key('add_action_${action.route}')));
        await tester.pumpAndSettle();

        // The pushed screen has its own title bar. The three capture screens are real since
        // P04 (tested in test/features/capture); the other two still say "coming soon".
        expect(
          find.descendant(
            of: find.byType(AppBar),
            matching: find.text(action.title),
          ),
          findsOneWidget,
        );
        if (!action.route.startsWith('/capture/')) {
          expect(find.text('Bu özellik yakında'), findsOneWidget);
        }
        expect(
          find.byKey(const Key('nav_add_button')),
          findsNothing,
        ); // no bottom bar here

        await tester.tap(find.byType(BackButton));
        await tester.pumpAndSettle();
        expect(find.text('Henüz harcama yok'), findsOneWidget); // back on Home
      });
    }
  });

  testWidgets('Home has a settings button that opens Settings', (tester) async {
    await _openSignedInApp(tester);

    await tester.tap(find.byTooltip('Ayarlar'));
    await tester.pumpAndSettle();

    expect(
      find.descendant(of: find.byType(AppBar), matching: find.text('Ayarlar')),
      findsOneWidget,
    );
  });
}
