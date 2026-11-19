import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/features/transactions/domain/purchase_models.dart';
import 'package:receiptbox/features/transactions/domain/spending_category.dart';

import '../../support/fakes.dart';

Future<TestApp> _openList(
  WidgetTester tester, {
  void Function(TestApp app)? seed,
}) async {
  tester.view.physicalSize = const Size(800, 2000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final app = await TestApp.signedIn();
  seed?.call(app);
  await tester.pumpWidget(app.app());
  await tester.pumpAndSettle();
  await tester.tap(find.text('Harcamalar').last);
  await tester.pumpAndSettle();
  return app;
}

void main() {
  group('list', () {
    testWidgets('empty: says so and offers manual entry', (tester) async {
      await _openList(tester);
      expect(find.text('Henüz harcama yok'), findsOneWidget);
      expect(find.byKey(const Key('add_manual_button')), findsOneWidget);
    });

    testWidgets('groups by day, newest first, with count and total', (
      tester,
    ) async {
      await _openList(
        tester,
        seed: (app) {
          app.transactions
            ..add(merchant: 'Migros', date: DateTime(2026, 11, 14), totalMinor: 27030)
            ..add(merchant: 'Shell', category: SpendingCategory.fuel, date: DateTime(2026, 11, 14), totalMinor: 150000)
            ..add(merchant: 'Teknosa', category: SpendingCategory.technology, date: DateTime(2026, 11, 2), totalMinor: 249900);
        },
      );

      expect(find.text('14 Kasım 2026'), findsOneWidget);
      expect(find.text('02 Kasım 2026'), findsOneWidget);
      expect(find.text('Migros'), findsOneWidget);
      expect(find.text('Teknosa'), findsOneWidget);
      expect(find.text('Yakıt'), findsOneWidget);
      expect(find.text('3 harcama'), findsOneWidget);
      expect(find.text('4.269,30 TL'), findsOneWidget); // the net total of all three
      expect(find.text('2.499,00 TL'), findsOneWidget);
    });

    testWidgets('filtering by category shows the filtered count and total', (
      tester,
    ) async {
      final app = await _openList(
        tester,
        seed: (app) {
          app.transactions
            ..add(merchant: 'Migros', totalMinor: 10000)
            ..add(merchant: 'BIM', totalMinor: 5000)
            ..add(merchant: 'Shell', category: SpendingCategory.fuel, totalMinor: 90000);
        },
      );

      await tester.tap(find.byKey(const Key('filter_category')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('category_GROCERY')));
      await tester.pumpAndSettle();

      expect(app.transactions.listCalls.last.category, SpendingCategory.grocery);
      expect(find.text('Filtreye uyan 2 harcama'), findsOneWidget);
      expect(find.text('150,00 TL'), findsOneWidget);
      expect(find.text('Shell'), findsNothing);

      await tester.tap(find.byKey(const Key('filter_clear')));
      await tester.pumpAndSettle();
      expect(find.text('Shell'), findsOneWidget);
      expect(find.text('3 harcama'), findsOneWidget);
    });

    testWidgets('search sends the text after a short pause', (tester) async {
      final app = await _openList(
        tester,
        seed: (app) {
          app.transactions
            ..add(merchant: 'Migros')
            ..add(merchant: 'Shell');
        },
      );

      await tester.enterText(find.byKey(const Key('search_field')), 'shel');
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();

      expect(app.transactions.listCalls.last.search, 'shel');
      expect(find.text('Shell'), findsOneWidget);
      expect(find.text('Migros'), findsNothing);
    });

    testWidgets('a filter without results says so', (tester) async {
      await _openList(
        tester,
        seed: (app) => app.transactions.add(merchant: 'Migros'),
      );
      await tester.enterText(find.byKey(const Key('search_field')), 'xyz');
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pumpAndSettle();
      expect(find.text('Bu filtreye uyan harcama yok'), findsOneWidget);
    });

    testWidgets('more pages are loaded with the button', (tester) async {
      final app = await _openList(
        tester,
        seed: (app) {
          for (var i = 0; i < 35; i++) {
            app.transactions.add(
              merchant: 'Dükkan $i',
              date: DateTime(2026, 10, 1).add(Duration(days: i)),
            );
          }
        },
      );
      expect(find.text('35 harcama'), findsOneWidget);
      final more = find.byKey(const Key('load_more'));
      await tester.dragUntilVisible(
        more,
        find.byKey(const Key('purchase_list')),
        const Offset(0, -300),
      );
      await tester.tap(more);
      await tester.pumpAndSettle();

      expect(app.transactions.listCalls.last.offset, 30);
      expect(find.byKey(const Key('load_more')), findsNothing); // all loaded
    });

    testWidgets('tapping a purchase opens its detail', (tester) async {
      await _openList(
        tester,
        seed: (app) => app.transactions.add(id: 'tx-9', merchant: 'Migros'),
      );
      await tester.tap(find.byKey(const Key('purchase_tx-9')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('detail_total')), findsOneWidget);
    });
  });

  group('detail', () {
    Future<TestApp> openDetail(WidgetTester tester, PurchaseDetail Function(TestApp) seed) async {
      late String id;
      final app = await _openList(tester, seed: (a) => id = seed(a).purchase.id);
      await tester.tap(find.byKey(Key('purchase_$id')));
      await tester.pumpAndSettle();
      return app;
    }

    testWidgets('shows amount, category, evidence chips and the lines', (
      tester,
    ) async {
      await openDetail(
        tester,
        (app) => app.transactions.add(
          merchant: 'Migros',
          totalMinor: 27030,
          evidence: const [EvidenceKind.receipt, EvidenceKind.bank],
          lines: const [
            ReceiptLine(name: 'SUT 1L', quantity: '1', totalMinor: 10000),
            ReceiptLine(name: 'EKMEK', quantity: '1', totalMinor: 17030),
          ],
          note: 'Haftalık alışveriş',
        ),
      );

      expect(find.text('270,30 TL'), findsOneWidget);
      expect(find.text('Market'), findsOneWidget);
      expect(find.byKey(const Key('evidence_receipt')), findsOneWidget);
      expect(find.byKey(const Key('evidence_bank')), findsOneWidget);
      expect(find.byKey(const Key('evidence_einvoice')), findsNothing);
      expect(find.text('Kalemler (2)'), findsOneWidget);
      expect(find.text('SUT 1L'), findsOneWidget);
      expect(find.text('Haftalık alışveriş'), findsOneWidget);
    });

    testWidgets('a stored receipt image is shown and opens full screen', (
      tester,
    ) async {
      await openDetail(
        tester,
        (app) => app.transactions.add(
          documents: const [
            DocumentInfo(id: 'doc-1', type: 'RECEIPT_IMAGE', mimeType: 'image/jpeg'),
          ],
        ),
      );

      expect(find.text('Belgeler'), findsOneWidget);
      expect(find.byType(Image), findsOneWidget);
      await tester.tap(find.byKey(const Key('document_doc-1')));
      await tester.pumpAndSettle();
      expect(find.text('Belge'), findsOneWidget);
      expect(find.byType(InteractiveViewer), findsWidgets);
    });

    testWidgets('delete asks first, then removes the purchase', (tester) async {
      final app = await openDetail(
        tester,
        (app) => app.transactions.add(id: 'tx-5', merchant: 'Migros'),
      );

      await tester.tap(find.byKey(const Key('delete_button')));
      await tester.pumpAndSettle();
      expect(find.text('Harcama silinsin mi?'), findsOneWidget);
      expect(app.transactions.deleted, isEmpty);

      await tester.tap(find.byKey(const Key('delete_confirm')));
      await tester.pumpAndSettle();

      expect(app.transactions.deleted, ['tx-5']);
      expect(find.text('Harcama silindi.'), findsOneWidget);
      expect(find.text('Henüz harcama yok'), findsOneWidget); // back on an empty list
    });

    testWidgets('edit changes the saved purchase', (tester) async {
      final app = await openDetail(
        tester,
        (app) => app.transactions.add(id: 'tx-6', merchant: 'Migros', totalMinor: 10000),
      );

      await tester.tap(find.byKey(const Key('edit_button')));
      await tester.pumpAndSettle();
      expect(find.text('Harcamayı düzenle'), findsOneWidget);
      await tester.enterText(find.byKey(const Key('field_total')), '125,50');
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('manual_save')));
      await tester.pumpAndSettle();

      final update = app.transactions.updated.single;
      expect(update.id, 'tx-6');
      expect(update.input.totalMinor, 12550);
      expect(update.input.merchant, 'Migros');
      expect(find.text('125,50 TL'), findsOneWidget); // the detail shows the new amount
    });
  });

  group('manual entry', () {
    testWidgets('the form saves a manual purchase and shows it in the list', (
      tester,
    ) async {
      final app = await _openList(tester);
      await tester.tap(find.byKey(const Key('add_manual_button')));
      await tester.pumpAndSettle();

      final save = find.byKey(const Key('manual_save'));
      expect(tester.widget<FilledButton>(save).onPressed, isNull); // nothing typed yet

      await tester.enterText(find.byKey(const Key('field_merchant')), 'Kırtasiye');
      await tester.enterText(find.byKey(const Key('field_total')), '1.249,90');
      await tester.enterText(find.byKey(const Key('field_note')), 'Defter ve kalem');
      await tester.tap(find.byKey(const Key('field_category')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('category_EDUCATION')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Online'));
      await tester.pumpAndSettle();
      await tester.tap(save);
      await tester.pumpAndSettle();

      final input = app.transactions.created.single;
      expect(input.merchant, 'Kırtasiye');
      expect(input.totalMinor, 124990);
      expect(input.category, SpendingCategory.education);
      expect(input.channel, PurchaseChannel.online);
      expect(input.note, 'Defter ve kalem');
      expect(find.text('Harcama kaydedildi.'), findsOneWidget);
      expect(find.text('Kırtasiye'), findsOneWidget);
    });

    testWidgets('a server error is shown and the form stays', (tester) async {
      final app = await _openList(tester);
      await tester.tap(find.byKey(const Key('add_manual_button')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const Key('field_merchant')), 'Bakkal');
      await tester.enterText(find.byKey(const Key('field_total')), '10');
      app.transactions.writeError = apiError('NETWORK_UNREACHABLE');
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('manual_save')));
      await tester.pumpAndSettle();

      expect(find.text('Manuel Harcama'), findsOneWidget);
      expect(find.text(messageForCodeForTest('NETWORK_UNREACHABLE')), findsOneWidget);
    });
  });
}

String messageForCodeForTest(String code) => apiError(code).message;
