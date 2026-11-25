import '../../transactions/domain/spending_category.dart';

/// "2026-11" -> 1 November 2026.
DateTime monthFromApi(String text) {
  final parts = text.split('-').map(int.parse).toList();
  return DateTime(parts[0], parts[1]);
}

/// 1 November 2026 -> "2026-11".
String monthToApi(DateTime month) =>
    '${month.year.toString().padLeft(4, '0')}-${month.month.toString().padLeft(2, '0')}';

SpendingCategory _category(Object? key) =>
    SpendingCategory.fromKey(key as String?) ?? SpendingCategory.other;

/// One category's net spending (backend `CategoryAmount`).
class CategoryAmount {
  const CategoryAmount({required this.category, required this.totalMinor});

  final SpendingCategory category;
  final int totalMinor;

  factory CategoryAmount.fromJson(Map<String, dynamic> json) => CategoryAmount(
    category: _category(json['category_key']),
    totalMinor: json['total_minor'] as int,
  );
}

/// The spending view of one month: purchases by purchase month, net of refunds. Installment
/// payments are never part of it.
class SpendingSummary {
  const SpendingSummary({
    required this.month,
    required this.totalMinor,
    required this.previousMonth,
    required this.previousTotalMinor,
    required this.changeMinor,
    required this.changePct,
    required this.byCategory,
  });

  final DateTime month;
  final int totalMinor;
  final DateTime previousMonth;
  final int previousTotalMinor;
  final int changeMinor;

  /// Null when the previous month had no spending.
  final double? changePct;
  final List<CategoryAmount> byCategory;

  factory SpendingSummary.fromJson(Map<String, dynamic> json) =>
      SpendingSummary(
        month: monthFromApi(json['month'] as String),
        totalMinor: json['total_minor'] as int,
        previousMonth: monthFromApi(json['previous_month'] as String),
        previousTotalMinor: json['previous_total_minor'] as int,
        changeMinor: json['change_minor'] as int,
        changePct: (json['change_pct'] as num?)?.toDouble(),
        byCategory: [
          for (final c in json['by_category'] as List<dynamic>)
            CategoryAmount.fromJson(c as Map<String, dynamic>),
        ],
      );
}

enum BudgetState {
  ok,
  warning,
  over;

  static BudgetState fromKey(String? key) => switch (key) {
    'OVER' => BudgetState.over,
    'WARNING' => BudgetState.warning,
    _ => BudgetState.ok,
  };
}

/// A category's monthly limit and its use (backend `BudgetOut`).
class BudgetUsage {
  const BudgetUsage({
    required this.category,
    required this.limitMinor,
    required this.spentMinor,
    required this.pct,
    required this.state,
  });

  final SpendingCategory category;
  final int limitMinor;
  final int spentMinor;

  /// Whole percent, rounded down.
  final int pct;
  final BudgetState state;

  factory BudgetUsage.fromJson(Map<String, dynamic> json) => BudgetUsage(
    category: _category(json['category_key']),
    limitMinor: json['monthly_limit_minor'] as int,
    spentMinor: json['spent_minor'] as int,
    pct: json['pct'] as int,
    state: BudgetState.fromKey(json['state'] as String?),
  );
}

enum AttentionType { returnWindow, warranty, budget }

/// Something to look at soon. Returns and warranties arrive with P12.
class AttentionItem {
  const AttentionItem({required this.type, this.budget});

  final AttentionType type;
  final BudgetUsage? budget;

  factory AttentionItem.fromJson(Map<String, dynamic> json) => AttentionItem(
    type: switch (json['type']) {
      'RETURN' => AttentionType.returnWindow,
      'WARRANTY' => AttentionType.warranty,
      _ => AttentionType.budget,
    },
    budget: json['budget'] == null
        ? null
        : BudgetUsage.fromJson(json['budget'] as Map<String, dynamic>),
  );
}

/// One installment payment due in the month (a payment, NOT spending).
class DuePayment {
  const DuePayment({
    required this.transactionId,
    required this.merchant,
    required this.category,
    required this.seq,
    required this.count,
    required this.amountMinor,
    required this.isEstimated,
  });

  final String transactionId;
  final String merchant;
  final SpendingCategory? category;
  final int seq;
  final int count;
  final int amountMinor;
  final bool isEstimated;

  factory DuePayment.fromJson(Map<String, dynamic> json) => DuePayment(
    transactionId: json['transaction_id'] as String,
    merchant: json['merchant_display'] as String,
    category: SpendingCategory.fromKey(json['category_key'] as String?),
    seq: json['seq'] as int,
    count: json['count'] as int,
    amountMinor: json['amount_minor'] as int,
    isEstimated: json['is_estimated'] as bool? ?? false,
  );
}

class MonthTotal {
  const MonthTotal({required this.month, required this.totalMinor});

  final DateTime month;
  final int totalMinor;

  factory MonthTotal.fromJson(Map<String, dynamic> json) => MonthTotal(
    month: monthFromApi(json['month'] as String),
    totalMinor: json['total_minor'] as int,
  );
}

/// The home screen of one month, in its fixed order (spec 11.1).
class HomeData {
  const HomeData({
    required this.month,
    required this.spending,
    required this.attention,
    required this.dueTotalMinor,
    required this.duePayments,
    required this.nextMonths,
  });

  final DateTime month;
  final SpendingSummary spending;
  final List<AttentionItem> attention;
  final int dueTotalMinor;
  final List<DuePayment> duePayments;

  /// The payments of this month and the next five.
  final List<MonthTotal> nextMonths;

  factory HomeData.fromJson(Map<String, dynamic> json) {
    final due = json['due_this_month'] as Map<String, dynamic>;
    return HomeData(
      month: monthFromApi(json['month'] as String),
      spending: SpendingSummary.fromJson(
        json['spending'] as Map<String, dynamic>,
      ),
      attention: [
        for (final a in json['attention'] as List<dynamic>)
          AttentionItem.fromJson(a as Map<String, dynamic>),
      ],
      dueTotalMinor: due['total_minor'] as int,
      duePayments: [
        for (final p in due['payments'] as List<dynamic>)
          DuePayment.fromJson(p as Map<String, dynamic>),
      ],
      nextMonths: [
        for (final m in json['next_months'] as List<dynamic>)
          MonthTotal.fromJson(m as Map<String, dynamic>),
      ],
    );
  }
}

/// One group of the spending view (a merchant, a month, a week ...).
class SpendingGroup {
  const SpendingGroup({
    required this.key,
    required this.label,
    required this.totalMinor,
  });

  final String key;
  final String label;
  final int totalMinor;

  factory SpendingGroup.fromJson(Map<String, dynamic> json) => SpendingGroup(
    key: json['key'] as String,
    label: json['label'] as String,
    totalMinor: json['total_minor'] as int,
  );
}

class SpendingGroups {
  const SpendingGroups({required this.totalMinor, required this.groups});

  final int totalMinor;
  final List<SpendingGroup> groups;

  factory SpendingGroups.fromJson(Map<String, dynamic> json) => SpendingGroups(
    totalMinor: json['total_minor'] as int,
    groups: [
      for (final g in json['groups'] as List<dynamic>)
        SpendingGroup.fromJson(g as Map<String, dynamic>),
    ],
  );
}

class CategoryChange {
  const CategoryChange({
    required this.category,
    required this.aMinor,
    required this.bMinor,
    required this.deltaMinor,
  });

  final SpendingCategory category;
  final int aMinor;
  final int bMinor;
  final int deltaMinor;

  factory CategoryChange.fromJson(Map<String, dynamic> json) => CategoryChange(
    category: _category(json['category_key']),
    aMinor: json['a_minor'] as int,
    bMinor: json['b_minor'] as int,
    deltaMinor: json['delta_minor'] as int,
  );
}

/// Period `a` (the one looked at) compared with period `b` (the one before).
class Comparison {
  const Comparison({
    required this.aTotalMinor,
    required this.bTotalMinor,
    required this.deltaMinor,
    required this.deltaPct,
    required this.topCategories,
  });

  final int aTotalMinor;
  final int bTotalMinor;
  final int deltaMinor;
  final double? deltaPct;
  final List<CategoryChange> topCategories;

  factory Comparison.fromJson(Map<String, dynamic> json) => Comparison(
    aTotalMinor: (json['a'] as Map<String, dynamic>)['total_minor'] as int,
    bTotalMinor: (json['b'] as Map<String, dynamic>)['total_minor'] as int,
    deltaMinor: json['delta_minor'] as int,
    deltaPct: (json['delta_pct'] as num?)?.toDouble(),
    topCategories: [
      for (final c in json['top_categories'] as List<dynamic>)
        CategoryChange.fromJson(c as Map<String, dynamic>),
    ],
  );
}

class YearSummary {
  const YearSummary({
    required this.year,
    required this.totalMinor,
    required this.byCategory,
    required this.byMonth,
    required this.topMerchants,
  });

  final int year;
  final int totalMinor;
  final List<CategoryAmount> byCategory;
  final List<MonthTotal> byMonth;
  final List<SpendingGroup> topMerchants;

  factory YearSummary.fromJson(Map<String, dynamic> json) => YearSummary(
    year: json['year'] as int,
    totalMinor: json['total_minor'] as int,
    byCategory: [
      for (final c in json['by_category'] as List<dynamic>)
        CategoryAmount.fromJson(c as Map<String, dynamic>),
    ],
    byMonth: [
      for (final m in json['by_month'] as List<dynamic>)
        MonthTotal.fromJson(m as Map<String, dynamic>),
    ],
    topMerchants: [
      for (final g in json['top_merchants'] as List<dynamic>)
        SpendingGroup.fromJson(g as Map<String, dynamic>),
    ],
  );
}

/// The period the analytics screen shows.
enum AnalyticsPeriod {
  week('Hafta'),
  month('Ay'),
  year('Yıl');

  const AnalyticsPeriod(this.label);

  final String label;
}

/// The first and last day of the period that contains [day], and of the one before it.
({DateTime from, DateTime to, DateTime previousFrom, DateTime previousTo})
periodRange(AnalyticsPeriod period, DateTime day) {
  final today = DateTime(day.year, day.month, day.day);
  switch (period) {
    case AnalyticsPeriod.week:
      final monday = today.subtract(Duration(days: today.weekday - 1));
      return (
        from: monday,
        to: monday.add(const Duration(days: 6)),
        previousFrom: monday.subtract(const Duration(days: 7)),
        previousTo: monday.subtract(const Duration(days: 1)),
      );
    case AnalyticsPeriod.month:
      return (
        from: DateTime(today.year, today.month),
        to: DateTime(today.year, today.month + 1, 0),
        previousFrom: DateTime(today.year, today.month - 1),
        previousTo: DateTime(today.year, today.month, 0),
      );
    case AnalyticsPeriod.year:
      return (
        from: DateTime(today.year),
        to: DateTime(today.year, 12, 31),
        previousFrom: DateTime(today.year - 1),
        previousTo: DateTime(today.year - 1, 12, 31),
      );
  }
}
