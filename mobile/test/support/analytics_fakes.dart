import 'package:receiptbox/core/networking/api_error.dart';
import 'package:receiptbox/features/analytics/data/analytics_api.dart';
import 'package:receiptbox/features/analytics/domain/analytics_models.dart';
import 'package:receiptbox/features/transactions/domain/spending_category.dart';

/// An empty home screen of [month]: nothing spent, nothing due.
HomeData emptyHome(DateTime month) => HomeData(
  month: month,
  spending: SpendingSummary(
    month: month,
    totalMinor: 0,
    previousMonth: DateTime(month.year, month.month - 1),
    previousTotalMinor: 0,
    changeMinor: 0,
    changePct: null,
    byCategory: const [],
  ),
  attention: const [],
  dueTotalMinor: 0,
  duePayments: const [],
  nextMonths: [
    for (var i = 0; i < 6; i++)
      MonthTotal(month: DateTime(month.year, month.month + i), totalMinor: 0),
  ],
);

/// The analytics endpoints in memory. Tests put answers in [homes] (by month) and read back what
/// the app asked for.
class FakeAnalyticsApi implements AnalyticsApi {
  final Map<DateTime, HomeData> homes = {};
  final homeCalls = <DateTime>[];
  ApiError? homeError;

  List<BudgetUsage> budgetAnswer = [];
  final putBudgets = <({SpendingCategory category, int limitMinor})>[];
  final deletedBudgets = <SpendingCategory>[];

  SpendingGroups byCategory = const SpendingGroups(totalMinor: 0, groups: []);
  SpendingGroups byMerchant = const SpendingGroups(totalMinor: 0, groups: []);
  final spendingCalls = <({DateTime from, DateTime to, String groupBy})>[];
  Comparison comparison = const Comparison(
    aTotalMinor: 0,
    bTotalMinor: 0,
    deltaMinor: 0,
    deltaPct: null,
    topCategories: [],
  );
  String? commentaryAnswer;
  Object? commentaryError;
  YearSummary? yearAnswer;

  @override
  Future<HomeData> home(DateTime month) async {
    homeCalls.add(month);
    final error = homeError;
    if (error != null) throw error;
    return homes[month] ?? emptyHome(month);
  }

  @override
  Future<SpendingGroups> spending({
    required DateTime from,
    required DateTime to,
    required String groupBy,
    int? limit,
  }) async {
    spendingCalls.add((from: from, to: to, groupBy: groupBy));
    return groupBy == 'merchant' ? byMerchant : byCategory;
  }

  @override
  Future<Comparison> compare({
    required DateTime aFrom,
    required DateTime aTo,
    required DateTime bFrom,
    required DateTime bTo,
  }) async => comparison;

  @override
  Future<String?> commentary({
    required DateTime aFrom,
    required DateTime aTo,
    required DateTime bFrom,
    required DateTime bTo,
  }) async {
    final error = commentaryError;
    if (error != null) throw error;
    return commentaryAnswer;
  }

  @override
  Future<YearSummary> year(int year) async =>
      yearAnswer ??
      YearSummary(
        year: year,
        totalMinor: 0,
        byCategory: const [],
        byMonth: [
          for (var m = 1; m <= 12; m++)
            MonthTotal(month: DateTime(year, m), totalMinor: 0),
        ],
        topMerchants: const [],
      );

  @override
  Future<List<BudgetUsage>> budgets({DateTime? month}) async => [
    ...budgetAnswer,
  ];

  @override
  Future<List<BudgetUsage>> putBudget(
    SpendingCategory category,
    int limitMinor,
  ) async {
    putBudgets.add((category: category, limitMinor: limitMinor));
    return budgetAnswer;
  }

  @override
  Future<void> deleteBudget(SpendingCategory category) async {
    deletedBudgets.add(category);
  }
}
