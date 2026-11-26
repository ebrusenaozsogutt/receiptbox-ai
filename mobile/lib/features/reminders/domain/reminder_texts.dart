import 'reminder_models.dart';
import 'turkish_suffixes.dart';

/// What a notification says and where a tap leads.
class ReminderMessage {
  const ReminderMessage({
    required this.title,
    required this.body,
    required this.route,
  });

  final String title;
  final String body;

  /// A go_router location: the product, the installments or the budgets screen.
  final String route;
}

String _whenReturnEnds(int? days) {
  if (days == null) return 'yakında bitiyor';
  if (days <= 0) return 'bugün bitiyor';
  if (days == 1) return 'yarın bitiyor';
  return '$days gün sonra bitiyor';
}

/// The Turkish texts of spec 12 / P13, e.g. "AirPods'un garanti süresinin bitmesine 30 gün
/// kaldı." The numbers come from the backend (days before the deadline), never from an LLM.
ReminderMessage messageFor(Reminder reminder) {
  switch (reminder.type) {
    case ReminderType.warrantyExpiry:
      final name = reminder.productName;
      final subject = name == null ? 'Ürününün' : genitive(name);
      final days = reminder.daysBefore;
      return ReminderMessage(
        title: 'Garanti hatırlatması',
        body: days == null
            ? '$subject garanti süresi yakında bitiyor.'
            : '$subject garanti süresinin bitmesine $days gün kaldı.',
        route: '/products/${reminder.productId}',
      );
    case ReminderType.returnDeadline:
      final name = reminder.productName;
      final product = name == null ? 'ürününün' : genitive(name);
      final merchant = reminder.merchant;
      final subject = merchant == null || merchant.trim().isEmpty
          ? product
          : '${ablative(merchant)} aldığın $product';
      return ReminderMessage(
        title: 'İade hatırlatması',
        body:
            '${_capitalised(subject)} iade süresi ${_whenReturnEnds(reminder.daysBefore)}.',
        route: '/products/${reminder.productId}',
      );
    case ReminderType.installmentEnd:
      final merchant = reminder.merchant;
      return ReminderMessage(
        title: 'Son taksit',
        body: merchant == null || merchant.trim().isEmpty
            ? 'Taksitlerinin sonuncusu bu ay.'
            : '$merchant taksitlerinin sonuncusu bu ay.',
        route: '/installments',
      );
    case ReminderType.budget80:
    case ReminderType.budget100:
      final percent = reminder.type == ReminderType.budget80
          ? "%80'ine"
          : "%100'üne";
      final label = reminder.category?.label;
      return ReminderMessage(
        title: 'Bütçe uyarısı',
        body: label == null
            ? 'Bir bütçenin $percent ulaştın.'
            : '$label bütçenin $percent ulaştın.',
        route: '/budgets',
      );
  }
}

/// First letter in upper case, the Turkish way ('i' → 'İ', 'ı' → 'I').
String _capitalised(String text) {
  if (text.isEmpty) return text;
  final first = switch (text[0]) {
    'i' => 'İ',
    'ı' => 'I',
    final other => other.toUpperCase(),
  };
  return first + text.substring(1);
}
