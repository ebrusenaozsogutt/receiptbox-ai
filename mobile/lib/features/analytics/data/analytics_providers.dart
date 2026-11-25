import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../domain/analytics_models.dart';
import 'analytics_api.dart';

part 'analytics_providers.g.dart';

/// "Now" for the analytics screens (tests replace it to get fixed months).
@Riverpod(keepAlive: true)
DateTime Function() analyticsClock(Ref ref) => DateTime.now;

/// The month the home screen shows (the month picker changes it). Starts at this month.
@Riverpod(keepAlive: true)
class HomeMonth extends _$HomeMonth {
  @override
  DateTime build() {
    final now = ref.watch(analyticsClockProvider)();
    return DateTime(now.year, now.month);
  }

  void set(DateTime month) => state = DateTime(month.year, month.month);
}

/// The home screen of the chosen month. Invalidate it after anything that changes spending
/// (the Home tab does so whenever it is opened again).
@riverpod
Future<HomeData> homeData(Ref ref) {
  final month = ref.watch(homeMonthProvider);
  return ref.watch(analyticsApiProvider).home(month);
}

/// The budgets of this month (the budgets screen).
@riverpod
Future<List<BudgetUsage>> budgetList(Ref ref) =>
    ref.watch(analyticsApiProvider).budgets();

@riverpod
class AnalyticsPeriodController extends _$AnalyticsPeriodController {
  @override
  AnalyticsPeriod build() => AnalyticsPeriod.month;

  void set(AnalyticsPeriod period) => state = period;
}

/// Everything the analytics screen shows for the chosen period (the AI commentary is loaded on
/// its own: it is optional and may be slow).
class AnalyticsView {
  const AnalyticsView({
    required this.period,
    required this.from,
    required this.to,
    required this.byCategory,
    required this.topMerchants,
    required this.comparison,
    required this.byMonth,
  });

  final AnalyticsPeriod period;
  final DateTime from;
  final DateTime to;
  final SpendingGroups byCategory;
  final SpendingGroups topMerchants;
  final Comparison comparison;

  /// Only for the year: the twelve months.
  final List<MonthTotal> byMonth;
}

@riverpod
Future<AnalyticsView> analyticsView(Ref ref) async {
  final period = ref.watch(analyticsPeriodControllerProvider);
  final api = ref.watch(analyticsApiProvider);
  final range = periodRange(period, ref.watch(analyticsClockProvider)());
  final results = await Future.wait([
    api.spending(from: range.from, to: range.to, groupBy: 'category'),
    api.spending(
      from: range.from,
      to: range.to,
      groupBy: 'merchant',
      limit: 10,
    ),
    api.compare(
      aFrom: range.from,
      aTo: range.to,
      bFrom: range.previousFrom,
      bTo: range.previousTo,
    ),
    if (period == AnalyticsPeriod.year) api.year(range.from.year),
  ]);
  return AnalyticsView(
    period: period,
    from: range.from,
    to: range.to,
    byCategory: results[0] as SpendingGroups,
    topMerchants: results[1] as SpendingGroups,
    comparison: results[2] as Comparison,
    byMonth: period == AnalyticsPeriod.year
        ? (results[3] as YearSummary).byMonth
        : const [],
  );
}

/// The AI's one or two sentences about the comparison; null when there are none. Never fails:
/// the screen shows nothing instead of an error.
@riverpod
Future<String?> comparisonCommentary(Ref ref) async {
  final period = ref.watch(analyticsPeriodControllerProvider);
  final range = periodRange(period, ref.watch(analyticsClockProvider)());
  try {
    return await ref
        .watch(analyticsApiProvider)
        .commentary(
          aFrom: range.from,
          aTo: range.to,
          bFrom: range.previousFrom,
          bTo: range.previousTo,
        );
  } on Object {
    return null;
  }
}
