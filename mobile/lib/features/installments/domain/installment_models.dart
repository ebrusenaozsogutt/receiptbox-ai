DateTime _day(String iso) {
  final parts = iso.split('-').map(int.parse).toList();
  return DateTime(parts[0], parts[1], parts[2]);
}

/// Where one monthly payment stands (backend `InstallmentPaymentStatus`).
enum PaymentStatus {
  /// A bank row for this payment was seen.
  observed('Bankada görüldü'),

  /// An earlier payment, taken as paid because a later one was seen.
  inferred('Ödenmiş sayıldı'),

  /// Not seen on a bank statement yet.
  expected('Bekleniyor');

  const PaymentStatus(this.label);

  final String label;

  static PaymentStatus fromKey(String key) => switch (key) {
    'OBSERVED' => PaymentStatus.observed,
    'INFERRED' => PaymentStatus.inferred,
    _ => PaymentStatus.expected,
  };
}

enum PlanStatus {
  active,
  completed,
  cancelled;

  static PlanStatus fromKey(String key) => switch (key) {
    'COMPLETED' => PlanStatus.completed,
    'CANCELLED' => PlanStatus.cancelled,
    _ => PlanStatus.active,
  };
}

class PlanPayment {
  const PlanPayment({
    required this.seq,
    required this.dueMonth,
    required this.amountMinor,
    required this.status,
  });

  final int seq;

  /// The first day of the month the payment is due.
  final DateTime dueMonth;
  final int amountMinor;
  final PaymentStatus status;

  factory PlanPayment.fromJson(Map<String, dynamic> json) => PlanPayment(
    seq: json['seq'] as int,
    dueMonth: _day(json['due_month'] as String),
    amountMinor: json['amount_minor'] as int,
    status: PaymentStatus.fromKey(json['status'] as String),
  );
}

/// The installment plan of a purchase: one spending, `count` payments (spec 8).
class InstallmentPlan {
  const InstallmentPlan({
    required this.id,
    required this.count,
    required this.totalPayableMinor,
    required this.firstDueMonth,
    required this.status,
    required this.payments,
  });

  final String id;
  final int count;

  /// What the bank charges in all (more than the purchase total when there is interest).
  final int totalPayableMinor;
  final DateTime firstDueMonth;
  final PlanStatus status;
  final List<PlanPayment> payments;

  bool get isActive => status == PlanStatus.active;

  /// How many payments were seen on a bank statement.
  int get observedCount =>
      payments.where((p) => p.status == PaymentStatus.observed).length;

  factory InstallmentPlan.fromJson(Map<String, dynamic> json) =>
      InstallmentPlan(
        id: json['id'] as String,
        count: json['count'] as int,
        totalPayableMinor: json['total_payable_minor'] as int,
        firstDueMonth: _day(json['first_due_month'] as String),
        status: PlanStatus.fromKey(json['status'] as String),
        payments: [
          for (final p in json['payments'] as List<dynamic>)
            PlanPayment.fromJson(p as Map<String, dynamic>),
        ],
      );
}

/// One payment in the schedule: whose, which month, how much.
class ScheduleItem {
  const ScheduleItem({
    required this.transactionId,
    required this.merchant,
    required this.seq,
    required this.count,
    required this.dueMonth,
    required this.amountMinor,
    required this.status,
    required this.isEstimated,
  });

  final String transactionId;
  final String merchant;
  final int seq;
  final int count;
  final DateTime dueMonth;
  final int amountMinor;
  final PaymentStatus status;
  final bool isEstimated;

  factory ScheduleItem.fromJson(Map<String, dynamic> json) => ScheduleItem(
    transactionId: json['transaction_id'] as String,
    merchant: json['merchant_display'] as String,
    seq: json['seq'] as int,
    count: json['count'] as int,
    dueMonth: _day(json['due_month'] as String),
    amountMinor: json['amount_minor'] as int,
    status: PaymentStatus.fromKey(json['status'] as String),
    isEstimated: json['is_estimated'] as bool? ?? false,
  );
}

class ScheduleMonth {
  const ScheduleMonth({
    required this.month,
    required this.totalMinor,
    required this.expectedMinor,
    required this.items,
  });

  final DateTime month;
  final int totalMinor;

  /// Of the total: not seen on a bank statement yet.
  final int expectedMinor;
  final List<ScheduleItem> items;

  factory ScheduleMonth.fromJson(Map<String, dynamic> json) => ScheduleMonth(
    month: _day(json['month'] as String),
    totalMinor: json['total_minor'] as int,
    expectedMinor: json['expected_minor'] as int,
    items: [
      for (final i in json['items'] as List<dynamic>)
        ScheduleItem.fromJson(i as Map<String, dynamic>),
    ],
  );
}

/// The payments of the active plans by month. NOT spending: a purchase is counted once, in its
/// purchase month, by the purchase list.
class InstallmentSchedule {
  const InstallmentSchedule({
    required this.months,
    required this.remainingMinor,
  });

  final List<ScheduleMonth> months;

  /// Everything still expected from this month on, over all plans.
  final int remainingMinor;

  bool get isEmpty => months.every((m) => m.items.isEmpty);

  factory InstallmentSchedule.fromJson(Map<String, dynamic> json) =>
      InstallmentSchedule(
        months: [
          for (final m in json['months'] as List<dynamic>)
            ScheduleMonth.fromJson(m as Map<String, dynamic>),
        ],
        remainingMinor: json['remaining_minor'] as int,
      );
}

/// What the bank import review says about a row with an installment marker (nothing is saved).
enum InstallmentPreviewState { link, estimate, ask, suggest }

class InstallmentPreview {
  const InstallmentPreview({
    required this.state,
    required this.seq,
    required this.count,
    required this.merchant,
  });

  final InstallmentPreviewState state;
  final int seq;
  final int count;

  /// The purchase it will join (link, suggest), when known.
  final String? merchant;

  /// "Taksit 2/6 → MediaMarkt alışverişine bağlanacak".
  String get label {
    final head = 'Taksit $seq/$count';
    return switch (state) {
      InstallmentPreviewState.link =>
        merchant == null
            ? '$head → mevcut alışverişe bağlanacak'
            : '$head → $merchant alışverişine bağlanacak',
      InstallmentPreviewState.estimate =>
        '$head → tahmini alışveriş oluşturulacak',
      InstallmentPreviewState.ask =>
        '$head → birden fazla alışverişe uyuyor, kaydedince sorulacak',
      InstallmentPreviewState.suggest =>
        merchant == null
            ? 'Bir taksit olabilir: kaydedince sorulacak'
            : 'Bir taksit olabilir ($merchant · $count taksit): kaydedince sorulacak',
    };
  }

  factory InstallmentPreview.fromJson(Map<String, dynamic> json) {
    final transaction = json['transaction'] as Map<String, dynamic>?;
    return InstallmentPreview(
      state: switch (json['state']) {
        'LINK' => InstallmentPreviewState.link,
        'ASK' => InstallmentPreviewState.ask,
        'SUGGEST' => InstallmentPreviewState.suggest,
        _ => InstallmentPreviewState.estimate,
      },
      seq: json['seq'] as int,
      count: json['count'] as int,
      merchant: transaction?['merchant_display'] as String?,
    );
  }
}

/// A bank installment row that became a payment of a purchase (no spending was added).
class LinkedRow {
  const LinkedRow({
    required this.observationId,
    required this.seq,
    required this.count,
    required this.transactionId,
  });

  final String observationId;
  final int seq;
  final int count;
  final String transactionId;
}
