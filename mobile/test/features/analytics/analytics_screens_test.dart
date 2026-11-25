import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/features/analytics/domain/analytics_models.dart';
import 'package:receiptbox/features/transactions/domain/spending_category.dart';

import '../../support/fakes.dart';

Future<TestApp> _open(
  WidgetTester tester,
  String button, {
  void Function(TestApp app)? seed,
}) async {
  tester.view.physicalSize = const Size(800, 3000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final app = await TestApp.signedIn();
  seed?.call(app);
  await tester.pumpWidget(app.app());
  await tester.pumpAndSettle();
  await tester.tap(find.text('Harcamalar').last);
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('open_analytics')));
  await tester.pumpAndSettle();
  if (button.isNotEmpty) {
    await tester.tap(find.byKey(Key(button)));
    await tester.pumpAndSettle();
  }
  return app;
}

void _seed(TestApp app) {
  app.analytics
    ..byCategory = const SpendingGroups(
      totalMinor: 354000,
      groups: [
        SpendingGroup(key: 'GROCERY', label: 'Market', totalMinor: 304000),
        SpendingGroup(key: 'FUEL', label: 'Yakıt', totalMinor: 50000),
      ],
    )
    ..byMerchant = const SpendingGroups(
      totalMinor: 354000,
      groups: [
        SpendingGroup(key: 'Migros', label: 'Migros', totalMinor: 304000),
        SpendingGroup(key: 'Shell', label: 'Shell', totalMinor: 50000),
      ],
    )
    ..comparison = const Comparison(
      aTotalMinor: 354000,
      bTotalMinor: 152000,
      deltaMinor: 202000,
      deltaPct: 132.9,
      topCategories: [
        CategoryChange(
          category: SpendingCategory.grocery,
          aMinor: 304000,
          bMinor: 152000,
          deltaMinor: 152000,
        ),
      ],
    );
}

void main() {
  group('the analytics screen', () {
    testWidgets(
      'shows the month by category and merchant, and the comparison',
      (tester) async {
        final app = await _open(tester, '', seed: _seed);

        expect(find.text('Analiz'), findsOneWidget);
        expect(
          find.text('Kasım 2026'),
          findsOneWidget,
        ); // the period (fixed clock)
        expect(find.byKey(const Key('analytics_total')), findsOneWidget);
        expect(find.text('3.540,00 TL'), findsWidgets);
        expect(find.text('Migros'), findsOneWidget);
        expect(find.text('+2.020,00 TL (%132,9)'), findsOneWidget);
        expect(
          find.byKey(const Key('analytics_change_GROCERY')),
          findsOneWidget,
        );
        final calls = app.analytics.spendingCalls;
        expect(calls.first.from, DateTime(2026, 11));
        expect(calls.first.to, DateTime(2026, 11, 30));
      },
    );

    testWidgets('the AI sentence is shown when there is one', (tester) async {
      await _open(
        tester,
        '',
        seed: (app) {
          _seed(app);
          app.analytics.commentaryAnswer =
              'Bu ay harcaman Market yüzünden arttı.';
        },
      );
      expect(find.byKey(const Key('analytics_commentary')), findsOneWidget);
      expect(
        find.text('Bu ay harcaman Market yüzünden arttı.'),
        findsOneWidget,
      );
    });

    testWidgets('a failing AI shows nothing, the rest still works', (
      tester,
    ) async {
      await _open(
        tester,
        '',
        seed: (app) {
          _seed(app);
          app.analytics.commentaryError = Exception('down');
        },
      );
      expect(find.byKey(const Key('analytics_commentary')), findsNothing);
      expect(find.text('Migros'), findsOneWidget);
    });

    testWidgets('week and year use their own ranges', (tester) async {
      final app = await _open(tester, '', seed: _seed);

      await tester.tap(find.text('Hafta'));
      await tester.pumpAndSettle();
      final week = app.analytics.spendingCalls.last;
      expect(week.from, DateTime(2026, 11, 16)); // Monday of 20 November 2026
      expect(week.to, DateTime(2026, 11, 22));

      await tester.tap(find.text('Yıl'));
      await tester.pumpAndSettle();
      expect(app.analytics.spendingCalls.last.from, DateTime(2026));
      expect(find.byKey(const Key('analytics_months')), findsOneWidget);
    });
  });

  group('the budgets screen', () {
    testWidgets('lists every category and the limits with their use', (
      tester,
    ) async {
      await _open(
        tester,
        'open_budgets',
        seed: (app) => app.analytics.budgetAnswer = const [
          BudgetUsage(
            category: SpendingCategory.grocery,
            limitMinor: 600000,
            spentMinor: 510000,
            pct: 85,
            state: BudgetState.warning,
          ),
        ],
      );

      expect(find.text('Bütçeler'), findsWidgets);
      expect(find.text('%85 · 5.100,00 TL / 6.000,00 TL'), findsOneWidget);
      for (final category in SpendingCategory.values) {
        expect(find.byKey(Key('budget_${category.key}')), findsOneWidget);
      }
      expect(
        find.text('Bütçe ekle'),
        findsNWidgets(SpendingCategory.values.length - 1),
      );
    });

    testWidgets('a limit is typed and saved', (tester) async {
      final app = await _open(tester, 'open_budgets');

      await tester.tap(find.byKey(const Key('budget_FUEL')));
      await tester.pumpAndSettle();
      final save = find.byKey(const Key('budget_save'));
      expect(
        tester.widget<TextButton>(save).onPressed,
        isNull,
      ); // nothing typed yet
      await tester.enterText(
        find.byKey(const Key('budget_limit_field')),
        '2.500',
      );
      await tester.pump();
      await tester.tap(save);
      await tester.pumpAndSettle();

      expect(app.analytics.putBudgets.single, (
        category: SpendingCategory.fuel,
        limitMinor: 250000,
      ));
      expect(find.text('Yakıt bütçesi kaydedildi.'), findsOneWidget);
    });

    testWidgets('a limit can be deleted', (tester) async {
      final app = await _open(
        tester,
        'open_budgets',
        seed: (app) => app.analytics.budgetAnswer = const [
          BudgetUsage(
            category: SpendingCategory.home,
            limitMinor: 100000,
            spentMinor: 0,
            pct: 0,
            state: BudgetState.ok,
          ),
        ],
      );

      await tester.tap(find.byKey(const Key('budget_HOME')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('budget_delete')));
      await tester.pumpAndSettle();

      expect(app.analytics.deletedBudgets, [SpendingCategory.home]);
    });
  });

  test('period ranges', () {
    final week = periodRange(
      AnalyticsPeriod.week,
      DateTime(2026, 11, 1),
    ); // a Sunday
    expect(week.from, DateTime(2026, 10, 26));
    expect(week.previousTo, DateTime(2026, 10, 25));
    final month = periodRange(AnalyticsPeriod.month, DateTime(2026, 3, 31));
    expect(month.to, DateTime(2026, 3, 31));
    expect(month.previousFrom, DateTime(2026, 2));
    expect(month.previousTo, DateTime(2026, 2, 28));
    final year = periodRange(AnalyticsPeriod.year, DateTime(2026, 6, 1));
    expect(year.previousFrom, DateTime(2025));
  });
}
