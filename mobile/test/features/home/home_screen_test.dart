import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/core/networking/api_error.dart';
import 'package:receiptbox/features/analytics/domain/analytics_models.dart';
import 'package:receiptbox/features/home/presentation/home_widgets.dart';
import 'package:receiptbox/features/transactions/domain/spending_category.dart';

import '../../support/analytics_fakes.dart';
import '../../support/fakes.dart';

final november = DateTime(2026, 11);
final october = DateTime(2026, 10);

HomeData _november() => HomeData(
  month: november,
  spending: SpendingSummary(
    month: november,
    totalMinor: 1872000,
    previousMonth: october,
    previousTotalMinor: 1720000,
    changeMinor: 152000,
    changePct: 8.8,
    byCategory: const [
      CategoryAmount(category: SpendingCategory.grocery, totalMinor: 542000),
      CategoryAmount(category: SpendingCategory.technology, totalMinor: 479000),
      CategoryAmount(category: SpendingCategory.foodDrink, totalMinor: 238000),
      CategoryAmount(category: SpendingCategory.transport, totalMinor: 192000),
      CategoryAmount(category: SpendingCategory.other, totalMinor: 421000),
      CategoryAmount(category: SpendingCategory.fuel, totalMinor: 1000),
    ],
  ),
  attention: const [
    AttentionItem(
      type: AttentionType.budget,
      budget: BudgetUsage(
        category: SpendingCategory.grocery,
        limitMinor: 600000,
        spentMinor: 510000,
        pct: 85,
        state: BudgetState.warning,
      ),
    ),
  ],
  dueTotalMinor: 290817,
  duePayments: const [
    DuePayment(
      transactionId: 'tx-1',
      merchant: 'MediaMarkt',
      category: SpendingCategory.technology,
      seq: 2,
      count: 6,
      amountMinor: 208317,
      isEstimated: false,
    ),
    DuePayment(
      transactionId: 'tx-2',
      merchant: 'Trendyol',
      category: SpendingCategory.clothing,
      seq: 4,
      count: 9,
      amountMinor: 41250,
      isEstimated: false,
    ),
    DuePayment(
      transactionId: 'tx-3',
      merchant: 'Hepsiburada',
      category: SpendingCategory.home,
      seq: 5,
      count: 12,
      amountMinor: 41250,
      isEstimated: true,
    ),
  ],
  nextMonths: [
    for (final (i, total) in [
      290817,
      290817,
      290817,
      249567,
      82500,
      41250,
    ].indexed)
      MonthTotal(month: DateTime(2026, 11 + i), totalMinor: total),
  ],
);

Future<TestApp> _openHome(
  WidgetTester tester, {
  void Function(TestApp app)? seed,
}) async {
  tester.view.physicalSize = const Size(800, 3000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final app = await TestApp.signedIn();
  app.analytics.homes[november] = _november();
  seed?.call(app);
  await tester.pumpWidget(app.app());
  await tester.pumpAndSettle();
  return app;
}

void main() {
  setUpAll(() => initializeDateFormatting('tr_TR'));

  group('labels', () {
    test('the change chip reads like the Figma frame', () {
      expect(
        changeLabel(_november().spending),
        "↑ %8,8 · Ekim'e göre +1.520 TL",
      );
      final less = SpendingSummary(
        month: november,
        totalMinor: 100000,
        previousMonth: october,
        previousTotalMinor: 150000,
        changeMinor: -50000,
        changePct: -33.3,
        byCategory: const [],
      );
      expect(changeLabel(less), "↓ %33,3 · Ekim'e göre -500 TL");
    });

    test('nothing to compare with says so', () {
      expect(
        changeLabel(emptyHome(november).spending),
        'Bu ay henüz harcama yok',
      );
    });
  });

  group('the home screen', () {
    testWidgets('shows the Figma order: spending, attention, payments due', (
      tester,
    ) async {
      await _openHome(tester);

      expect(find.text('Kasım 2026'), findsOneWidget);
      expect(find.text('BU AYKİ HARCAMA'), findsOneWidget);
      expect(find.text('18.720,00 TL'), findsOneWidget);
      expect(find.text("↑ %8,8 · Ekim'e göre +1.520 TL"), findsOneWidget);
      // the order on screen is fixed (spec 11.1)
      final spending = tester
          .getTopLeft(find.byKey(const Key('home_spending')))
          .dy;
      final categories = tester
          .getTopLeft(find.byKey(const Key('home_categories')))
          .dy;
      final attention = tester
          .getTopLeft(find.byKey(const Key('home_attention')))
          .dy;
      final due = tester.getTopLeft(find.byKey(const Key('home_due'))).dy;
      expect(
        spending < categories && categories < attention && attention < due,
        isTrue,
      );
    });

    testWidgets('lists at most five categories, whole lira, largest bar full', (
      tester,
    ) async {
      await _openHome(tester);

      expect(find.text('5.420 TL'), findsOneWidget);
      expect(find.text('4.790 TL'), findsOneWidget);
      expect(find.byKey(const Key('home_category_GROCERY')), findsOneWidget);
      expect(
        find.byKey(const Key('home_category_FUEL')),
        findsNothing,
      ); // the sixth
    });

    testWidgets('a budget at 85 % is under "Dikkat gerektirenler"', (
      tester,
    ) async {
      await _openHome(tester);

      expect(find.text('Dikkat gerektirenler'), findsOneWidget);
      expect(find.text('Market bütçesi'), findsOneWidget);
      expect(find.text('%85 · 5.100 / 6.000 TL'), findsOneWidget);
      expect(find.byKey(const Key('home_attention_empty')), findsNothing);
    });

    testWidgets('the installments appear only under "Bu ay ödenecekler"', (
      tester,
    ) async {
      await _openHome(tester);

      expect(find.text('Bu ay ödenecekler'), findsOneWidget);
      expect(find.text('3 taksit'), findsOneWidget);
      expect(find.byKey(const Key('home_due_total')), findsOneWidget);
      expect(find.text('2.908,17 TL'), findsOneWidget);
      expect(find.text('Teknoloji · 2/6'), findsOneWidget);
      expect(find.text('Ev & Yaşam · 5/12 · tahmini'), findsOneWidget);
      expect(find.text('Önümüzdeki aylar'), findsOneWidget);
      for (final month in ['Kas', 'Ara', 'Oca', 'Şub', 'Mar', 'Nis']) {
        expect(find.text(month), findsOneWidget);
      }
      // the spending total is the backend's spending view: payments are not added to it
      expect(find.text('18.720,00 TL'), findsOneWidget);
    });

    testWidgets('the month picker switches months', (tester) async {
      final app = await _openHome(
        tester,
        seed: (app) => app.analytics.homes[october] = emptyHome(october),
      );

      await tester.tap(find.byKey(const Key('home_month_picker')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('month_2026-10')));
      await tester.pumpAndSettle();

      expect(find.text('Ekim 2026'), findsOneWidget);
      expect(find.text('EKIM 2026 HARCAMASI'), findsNothing);
      expect(find.text('EKİM 2026 HARCAMASI'), findsOneWidget);
      expect(find.text('0,00 TL'), findsWidgets);
      expect(find.text('Ekim 2026 ödemeleri'), findsOneWidget);
      expect(find.byKey(const Key('home_attention_empty')), findsOneWidget);
      expect(app.analytics.homeCalls.last, october);
    });

    testWidgets('months after next year are not offered', (tester) async {
      await _openHome(tester);
      await tester.tap(find.byKey(const Key('home_month_picker')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('month_next_year')));
      await tester.pumpAndSettle();

      final next = tester.widget<IconButton>(
        find.byKey(const Key('month_next_year')),
      );
      expect(next.onPressed, isNull); // 2027 is the last year
      final december = tester.widget<ChoiceChip>(
        find.byKey(const Key('month_2027-12')),
      );
      expect(december.onSelected, isNull); // after November 2027
    });

    testWidgets('"Tümü" opens the analytics screen', (tester) async {
      await _openHome(tester);
      await tester.tap(find.byKey(const Key('home_all_categories')));
      await tester.pumpAndSettle();
      expect(find.text('Analiz'), findsOneWidget);
    });

    testWidgets('an error can be retried', (tester) async {
      final app = await _openHome(
        tester,
        seed: (app) =>
            app.analytics.homeError = apiError('NETWORK_UNREACHABLE'),
      );

      expect(find.text(messageForCode('NETWORK_UNREACHABLE')), findsOneWidget);
      app.analytics.homeError = null;
      await tester.tap(find.text('Tekrar dene'));
      await tester.pumpAndSettle();
      expect(find.text('18.720,00 TL'), findsOneWidget);
    });

    testWidgets('opening the Home tab again loads the numbers again', (
      tester,
    ) async {
      final app = await _openHome(tester);
      final before = app.analytics.homeCalls.length;

      await tester.tap(find.text('Harcamalar').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Ana Sayfa').last);
      await tester.pumpAndSettle();

      expect(app.analytics.homeCalls.length, greaterThan(before));
    });
  });
}
