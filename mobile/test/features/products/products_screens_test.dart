import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/core/privacy/pii_masker.dart';
import 'package:receiptbox/features/analytics/domain/analytics_models.dart';
import 'package:receiptbox/features/capture/domain/bank_models.dart';
import 'package:receiptbox/features/capture/domain/capture_payload.dart';
import 'package:receiptbox/features/matching/domain/match_models.dart';
import 'package:receiptbox/features/products/domain/product_models.dart';
import 'package:receiptbox/features/transactions/domain/purchase_models.dart';
import 'package:receiptbox/features/transactions/domain/spending_category.dart';

import '../../support/analytics_fakes.dart';
import '../../support/fakes.dart';
import '../../support/product_fakes.dart';

Future<TestApp> _signedIn(
  WidgetTester tester, {
  void Function(TestApp app)? seed,
}) async {
  tester.view.physicalSize = const Size(800, 3000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final app = await TestApp.signedIn();
  seed?.call(app);
  await tester.pumpWidget(app.app());
  await tester.pumpAndSettle();
  return app;
}

Future<TestApp> _openProducts(
  WidgetTester tester, {
  void Function(TestApp app)? seed,
}) async {
  final app = await _signedIn(tester, seed: seed);
  await tester.tap(find.text('Ürünler').last);
  await tester.pumpAndSettle();
  return app;
}

Future<TestApp> _openProduct(WidgetTester tester, Product product) async {
  final app = await _openProducts(
    tester,
    seed: (app) => app.products.products.add(product),
  );
  await tester.tap(find.byKey(Key('product_${product.id}')));
  await tester.pumpAndSettle();
  return app;
}

ProductSuggestion _suggestion({String tx = 'tx-1'}) => ProductSuggestion(
  transactionId: tx,
  receiptItemId: null,
  name: 'Samsung TV',
  merchant: 'Teknosa',
  category: SpendingCategory.technology,
  purchaseDate: DateTime(2026, 11, 10),
  priceMinor: 1249900,
);

PurchaseDetail _detail({
  String id = 'tx-1',
  int total = 1249900,
  List<RefundEntry> refunds = const [],
  int? refundable,
  List<ProductSuggestion> suggestions = const [],
}) => PurchaseDetail(
  purchase: Purchase(
    id: id,
    merchant: 'Teknosa',
    category: SpendingCategory.technology,
    date: DateTime(2026, 11, 10),
    time: null,
    totalMinor: total,
    channel: PurchaseChannel.online,
    note: null,
    documentCount: 0,
    refundedMinor: refunds.fold(0, (s, r) => s + r.amountMinor),
  ),
  evidence: const [EvidenceKind.manual],
  lines: const [],
  documents: const [],
  refunds: refunds,
  refundableMinor:
      refundable ?? total - refunds.fold<int>(0, (s, r) => s + r.amountMinor),
  productSuggestions: suggestions,
);

void main() {
  setUpAll(() => initializeDateFormatting('tr_TR'));

  group('the Products tab', () {
    testWidgets(
      'lists suggestions, the Teknoloji Kasam by warranty and the rest',
      (tester) async {
        await _openProducts(
          tester,
          seed: (app) {
            app.products.suggestionAnswer = [_suggestion(tx: 'tx-9')];
            app.products.products.addAll([
              fakeProduct(
                id: 'p-late',
                name: 'Laptop',
                warranty: Warranty(
                  startDate: null,
                  endDate: DateTime(2028, 1, 1),
                  source: WarrantySource.legalDefault,
                  confirmed: true,
                  daysLeft: 400,
                ),
              ),
              fakeProduct(
                id: 'p-soon',
                name: 'AirPods',
                warranty: Warranty(
                  startDate: null,
                  endDate: DateTime(2026, 12, 10),
                  source: WarrantySource.legalDefault,
                  confirmed: true,
                  daysLeft: 20,
                ),
              ),
              fakeProduct(
                id: 'p-sofa',
                name: 'Koltuk',
                category: SpendingCategory.home,
              ),
            ]);
          },
        );

        expect(find.text('Öneriler'), findsOneWidget);
        expect(find.text('Teknoloji Kasam'), findsOneWidget);
        final soon = tester
            .getTopLeft(find.byKey(const Key('product_p-soon')))
            .dy;
        final late = tester
            .getTopLeft(find.byKey(const Key('product_p-late')))
            .dy;
        expect(soon < late, isTrue); // the warranty that ends first is on top
        expect(find.text('20 gün'), findsOneWidget);
        expect(
          find.descendant(
            of: find.byKey(const Key('other_products')),
            matching: find.text('Koltuk'),
          ),
          findsOneWidget,
        );
      },
    );

    testWidgets('"Takip et" makes the product and opens it', (tester) async {
      final app = await _openProducts(
        tester,
        seed: (app) => app.products.suggestionAnswer = [_suggestion()],
      );

      await tester.tap(find.byKey(const Key('suggestion_track_tx-1')));
      await tester.pumpAndSettle();

      expect(app.products.created.single.transactionId, 'tx-1');
      expect(find.text('Ürün'), findsOneWidget); // the product card
    });

    testWidgets('"Hayır, bir daha sorma" dismisses the suggestion', (
      tester,
    ) async {
      final app = await _openProducts(
        tester,
        seed: (app) => app.products.suggestionAnswer = [_suggestion()],
      );

      await tester.tap(find.byKey(const Key('suggestion_dismiss_tx-1')));
      await tester.pumpAndSettle();

      expect(app.products.dismissed.single.transactionId, 'tx-1');
      expect(find.text('Öneriler'), findsNothing);
    });

    testWidgets('filter chips show returned and archived products', (
      tester,
    ) async {
      await _openProducts(
        tester,
        seed: (app) => app.products.products.addAll([
          fakeProduct(id: 'p-a', name: 'Aktif TV'),
          fakeProduct(
            id: 'p-r',
            name: 'İade TV',
            status: ProductStatus.returned,
          ),
        ]),
      );

      await tester.tap(find.byKey(const Key('product_filter_returned')));
      await tester.pumpAndSettle();

      expect(find.text('İade TV'), findsOneWidget);
      expect(find.text('Aktif TV'), findsNothing);
    });
  });

  group('the product card', () {
    testWidgets('shows the defaults with their source labels', (tester) async {
      await _openProduct(tester, fakeProduct(financingCostMinor: 60000));

      expect(find.text('Samsung TV'), findsOneWidget);
      expect(find.text('12.499,00 TL'), findsOneWidget);
      expect(find.byKey(const Key('product_financing')), findsOneWidget);
      expect(find.text('ONAYLANMADI'), findsOneWidget);
      expect(
        find.text('Yasal asgari süre (2 yıl) — düzenleyebilirsin'),
        findsOneWidget,
      );
      expect(find.text('10 Kasım 2028 · 721 gün'), findsOneWidget);
      expect(find.text('24 Kasım 2026 · 4 gün'), findsOneWidget);
      expect(
        find.text(
          'Mesafeli satışta cayma hakkı (14 gün) — teslimden sayılır, düzenleyebilirsin',
        ),
        findsOneWidget,
      );
      for (final action in [
        'Belgeyi Gör',
        'İade Edildi',
        'Düzenle',
        'Arşivle',
      ]) {
        expect(find.text(action), findsOneWidget);
      }
    });

    testWidgets('"Onayla" accepts the legal default as it is', (tester) async {
      final app = await _openProduct(tester, fakeProduct());

      await tester.tap(find.byKey(const Key('warranty_confirm')));
      await tester.pumpAndSettle();

      expect(app.products.warranties.single, (
        id: 'p-1',
        end: DateTime(2028, 11, 10),
        source: WarrantySource.legalDefault,
      ));
    });

    testWidgets('an in-store purchase asks for the store return period', (
      tester,
    ) async {
      await _openProduct(
        tester,
        fakeProduct(channel: PurchaseChannel.inStore, noReturn: true),
      );

      expect(find.byKey(const Key('return_none')), findsOneWidget);
      expect(find.text('Mağazanın iade süresini gir'), findsOneWidget);
    });

    testWidgets('"Arşivle" archives the product', (tester) async {
      final app = await _openProduct(tester, fakeProduct());

      await tester.tap(find.byKey(const Key('product_archive')));
      await tester.pumpAndSettle();

      expect(app.products.patches.single.fields, {'status': 'ARCHIVED'});
    });

    testWidgets(
      '"İade Edildi" records a refund of the purchase for this product',
      (tester) async {
        final app = await _openProduct(tester, fakeProduct());
        app.products.refundAnswer = _detail();

        await tester.tap(find.byKey(const Key('product_returned')));
        await tester.pumpAndSettle();
        expect(find.byKey(const Key('refund_full_amount')), findsOneWidget);
        await tester.tap(find.byKey(const Key('refund_save')));
        await tester.pumpAndSettle();

        final refund = app.products.refunds.single;
        expect(
          (refund.transactionId, refund.amountMinor, refund.productId),
          ('tx-1', 1249900, 'p-1'),
        );
      },
    );
  });

  group('after saving a purchase', () {
    testWidgets('"Bunu ürün olarak takip edelim mi?" — Evet opens the product', (
      tester,
    ) async {
      final app = await _signedIn(tester);
      app.transactions.nextSave = Saved(_detail(suggestions: [_suggestion()]));
      await tester.tap(find.text('Harcamalar').last);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('add_manual_button')));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const Key('field_merchant')),
        'Teknosa',
      );
      await tester.enterText(find.byKey(const Key('field_total')), '12.499');
      await tester.pump();
      await tester.tap(find.byKey(const Key('manual_save')));
      // the save spinner keeps turning behind the question sheet: pump a little
      for (var i = 0; i < 10; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      expect(find.text('Bunu ürün olarak takip edelim mi?'), findsOneWidget);
      await tester.tap(find.byKey(const Key('track_yes')));
      await tester.pumpAndSettle();

      expect(app.products.created.single.transactionId, 'tx-1');
      expect(find.byKey(const Key('product_header')), findsOneWidget);
    });

    testWidgets('"Hayır, bir daha sorma" dismisses it', (tester) async {
      final app = await _signedIn(tester);
      app.transactions.nextSave = Saved(_detail(suggestions: [_suggestion()]));
      await tester.tap(find.text('Harcamalar').last);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('add_manual_button')));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const Key('field_merchant')),
        'Teknosa',
      );
      await tester.enterText(find.byKey(const Key('field_total')), '12.499');
      await tester.pump();
      await tester.tap(find.byKey(const Key('manual_save')));
      // the save spinner keeps turning behind the question sheet: pump a little
      for (var i = 0; i < 10; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      await tester.tap(find.byKey(const Key('track_never')));
      await tester.pumpAndSettle();

      expect(app.products.dismissed.single.transactionId, 'tx-1');
      expect(app.products.created, isEmpty);
    });
  });

  group('refunds on the purchase list and detail', () {
    testWidgets('a refunded purchase is shown net with its refund', (
      tester,
    ) async {
      final app = await _signedIn(tester);
      app.transactions.purchases.add(
        _detail(
          refunds: [
            RefundEntry(
              id: 'r-1',
              date: DateTime(2026, 11, 20),
              amountMinor: 250000,
            ),
          ],
        ),
      );
      await tester.tap(find.text('Harcamalar').last);
      await tester.pumpAndSettle();

      expect(find.text('9.999,00 TL'), findsWidgets);
      expect(find.text('İade: -2.500,00 TL'), findsOneWidget);

      await tester.tap(find.byKey(const Key('purchase_tx-1')));
      await tester.pumpAndSettle();
      expect(find.text('İade · 20 Kasım 2026'), findsOneWidget);
      expect(find.text('Harcamada sayılan: 9.999,00 TL'), findsOneWidget);
    });

    testWidgets('a partial refund is entered from the purchase', (
      tester,
    ) async {
      final app = await _signedIn(tester);
      app.transactions.purchases.add(_detail());
      app.products.refundAnswer = _detail();
      await tester.tap(find.text('Harcamalar').last);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('purchase_tx-1')));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('purchase_refund')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Bir kısmı'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const Key('refund_amount')), '20.000');
      await tester.pump();
      expect(
        find.text('En fazla 12.499,00 TL iade edilebilir.'),
        findsOneWidget,
      );
      await tester.enterText(find.byKey(const Key('refund_amount')), '2.500');
      await tester.pump();
      await tester.tap(find.byKey(const Key('refund_save')));
      await tester.pumpAndSettle();

      expect(app.products.refunds.single.amountMinor, 250000);
      expect(app.products.refunds.single.productId, isNull);
    });
  });

  group('the home screen', () {
    testWidgets('lists a return ending in 2 days and a warranty ending in 20', (
      tester,
    ) async {
      final month = DateTime(2026, 11);
      await _signedIn(
        tester,
        seed: (app) {
          final empty = emptyHome(month);
          app.analytics.homes[month] = HomeData(
            month: month,
            spending: empty.spending,
            attention: [
              AttentionItem(
                type: AttentionType.returnWindow,
                product: AttentionProduct(
                  productId: 'p-1',
                  name: 'Nike Air Zoom',
                  merchant: 'Trendyol',
                  endDate: DateTime(2026, 11, 22),
                  daysLeft: 2,
                ),
              ),
              AttentionItem(
                type: AttentionType.warranty,
                product: AttentionProduct(
                  productId: 'p-2',
                  name: 'AirPods Pro',
                  merchant: 'Teknosa',
                  endDate: DateTime(2026, 12, 10),
                  daysLeft: 20,
                ),
              ),
            ],
            dueTotalMinor: 0,
            duePayments: const [],
            nextMonths: empty.nextMonths,
          );
        },
      );

      expect(find.text('İADE'), findsOneWidget);
      expect(find.text('GARANTİ'), findsOneWidget);
      expect(find.text('Nike Air Zoom'), findsOneWidget);
      expect(find.text('Trendyol · iade son günü 22 Kasım'), findsOneWidget);
      expect(find.text('2 gün'), findsOneWidget);
      expect(find.text('Teknosa · garanti bitişi 10 Aralık'), findsOneWidget);
      expect(find.text('20 gün'), findsOneWidget);
    });
  });

  group('a bank CREDIT row', () {
    testWidgets(
      'is suggested as a refund and linked only when the user says so',
      (tester) async {
        tester.view.physicalSize = const Size(800, 3000);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        final base = await TestApp.signedIn();
        final app = await TestApp.create(
          api: base.api,
          tokens: base.tokens,
          preferences: {
            'consent_seen': true,
            'has_account': true,
            'ai_consent': true,
          },
        );
        app.api.serverAiConsent = true;
        await tester.pumpWidget(app.app());
        await tester.pumpAndSettle();
        app.extraction.bankResult = BankImport(
          bankKey: BankKey.garanti,
          rows: [
            BankRow(
              observationId: 'c-1',
              merchant: 'TEKNOSA KONYA',
              amountMinor: 349900,
              isCredit: true,
              kind: BankRowKind.refund,
              date: DateTime(2026, 11, 20),
              installmentSeq: null,
              installmentCount: null,
              isPending: false,
              isDuplicate: false,
              confidence: const {
                'merchant': 'HIGH',
                'amount': 'HIGH',
                'date': 'HIGH',
                'installment': 'HIGH',
              },
              category: SpendingCategory.other,
            ),
          ],
          skipped: const [],
        );
        app.products.refundSuggestionAnswer = [
          RefundSuggestion(
            observationId: 'c-1',
            merchant: 'TEKNOSA KONYA',
            amountMinor: 349900,
            date: DateTime(2026, 11, 20),
            candidates: [
              RefundCandidate(
                transactionId: 'tx-7',
                merchant: 'Teknosa',
                purchaseDate: DateTime(2026, 11, 11),
                totalMinor: 349900,
                refundableMinor: 349900,
              ),
            ],
          ),
        ];
        app.products.refundAnswer = _detail(id: 'tx-7');
        app.pipeline.result = CaptureResult(
          payload: CapturePayload(
            kind: CaptureKind.bankScreenshot,
            maskedText: 'BONUS DIJI Gerçekleşen Hareketler',
            captureDate: DateTime(2026, 11, 20),
            source: CaptureSource.gallery,
          ),
          maskedCounts: const {PiiType.phone: 1},
          pageCount: 1,
        );
        await tester.tap(find.byKey(const Key('nav_add_button')));
        await tester.pumpAndSettle();
        await tester.tap(find.byKey(const Key('add_action_/capture/gallery')));
        await tester.pumpAndSettle();
        await tester.tap(find.byKey(const Key('pick_image_button')));
        await tester.pumpAndSettle();
        await tester.tap(find.byKey(const Key('kind_bank')));
        await tester.pumpAndSettle();

        expect(
          find.text('Teknosa alışverişinin iadesi olabilir'),
          findsOneWidget,
        );
        expect(app.products.linked, isEmpty); // nothing happens by itself

        await tester.tap(find.byKey(const Key('refund_link_button_c-1')));
        await tester.pumpAndSettle();
        expect(
          find.text(
            'Bu para iadesi Teknosa alışverişine ait olabilir. İade olarak bağlansın mı?',
          ),
          findsOneWidget,
        );
        await tester.tap(find.byKey(const Key('refund_link_tx-7')));
        await tester.pumpAndSettle();

        expect(app.products.linked.single, (
          observationId: 'c-1',
          transactionId: 'tx-7',
        ));
        expect(find.text('İade olarak bağlandı'), findsOneWidget);
      },
    );
  });
}
