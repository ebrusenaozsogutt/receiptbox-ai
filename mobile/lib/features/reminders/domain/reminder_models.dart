import '../../transactions/domain/spending_category.dart';

/// The four kinds of notification the user can switch on or off in Settings (spec 12).
enum ReminderKind {
  warranty('Garanti'),
  returnWindow('İade'),
  installment('Taksit'),
  budget('Bütçe');

  const ReminderKind(this.label);

  final String label;
}

/// Backend `ReminderType`.
enum ReminderType {
  warrantyExpiry('WARRANTY_EXPIRY', ReminderKind.warranty),
  returnDeadline('RETURN_DEADLINE', ReminderKind.returnWindow),
  installmentEnd('INSTALLMENT_END', ReminderKind.installment),
  budget80('BUDGET_80', ReminderKind.budget),
  budget100('BUDGET_100', ReminderKind.budget);

  const ReminderType(this.key, this.kind);

  final String key;
  final ReminderKind kind;

  static ReminderType? fromKey(String? key) {
    for (final type in values) {
      if (type.key == key) return type;
    }
    return null;
  }
}

DateTime? _dayOrNull(Object? iso) {
  if (iso == null) return null;
  final parts = (iso as String).split('-').map(int.parse).toList();
  return DateTime(parts[0], parts[1], parts[2]);
}

/// One reminder from `GET /reminders/upcoming` (backend `ReminderOut`).
class Reminder {
  const Reminder({
    required this.id,
    required this.type,
    required this.fireAt,
    this.deadline,
    this.daysBefore,
    this.productId,
    this.productName,
    this.transactionId,
    this.merchant,
    this.category,
  });

  final String id;
  final ReminderType type;

  /// When to notify (an instant; the backend sends it with its UTC offset).
  final DateTime fireAt;
  final DateTime? deadline;
  final int? daysBefore;
  final String? productId;
  final String? productName;
  final String? transactionId;
  final String? merchant;
  final SpendingCategory? category;

  /// Null when the backend sent a type this app does not know (it is then skipped).
  static Reminder? fromJson(Map<String, dynamic> json) {
    final type = ReminderType.fromKey(json['type'] as String?);
    if (type == null) return null;
    return Reminder(
      id: json['id'] as String,
      type: type,
      fireAt: DateTime.parse(json['fire_at'] as String),
      deadline: _dayOrNull(json['deadline']),
      daysBefore: json['days_before'] as int?,
      productId: json['product_id'] as String?,
      productName: json['product_name'] as String?,
      transactionId: json['transaction_id'] as String?,
      merchant: json['merchant_display'] as String?,
      category: SpendingCategory.fromKey(json['category_key'] as String?),
    );
  }
}
