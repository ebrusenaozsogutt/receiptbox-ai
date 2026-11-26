import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/features/reminders/domain/reminder_models.dart';
import 'package:receiptbox/features/reminders/domain/reminder_texts.dart';
import 'package:receiptbox/features/reminders/domain/turkish_suffixes.dart';
import 'package:receiptbox/features/transactions/domain/spending_category.dart';

Reminder reminder(
  ReminderType type, {
  String? name,
  String? merchant,
  int? days,
  SpendingCategory? category,
}) => Reminder(
  id: 'r-1',
  type: type,
  fireAt: DateTime.utc(2026, 12, 1, 7),
  daysBefore: days,
  productId: 'p-1',
  productName: name,
  transactionId: 'tx-1',
  merchant: merchant,
  category: category,
);

void main() {
  group('the texts of the phase file', () {
    test('warranty', () {
      final message = messageFor(
        reminder(ReminderType.warrantyExpiry, name: 'AirPods', days: 30),
      );
      expect(
        message.body,
        "AirPods'un garanti süresinin bitmesine 30 gün kaldı.",
      );
      expect(message.route, '/products/p-1');
    });

    test('return, the day before', () {
      final message = messageFor(
        reminder(
          ReminderType.returnDeadline,
          name: 'ayakkabı',
          merchant: 'Trendyol',
          days: 1,
        ),
      );
      expect(
        message.body,
        "Trendyol'dan aldığın ayakkabının iade süresi yarın bitiyor.",
      );
      expect(message.route, '/products/p-1');
    });

    test('budget 80 %', () {
      final message = messageFor(
        reminder(ReminderType.budget80, category: SpendingCategory.grocery),
      );
      expect(message.body, "Market bütçenin %80'ine ulaştın.");
      expect(message.route, '/budgets');
    });

    test('last installment', () {
      final message = messageFor(
        reminder(ReminderType.installmentEnd, merchant: 'MediaMarkt', days: 0),
      );
      expect(message.body, 'MediaMarkt taksitlerinin sonuncusu bu ay.');
      expect(message.route, '/installments');
    });
  });

  group('other cases', () {
    test('return 3 days before, without a shop', () {
      expect(
        messageFor(
          reminder(
            ReminderType.returnDeadline,
            name: 'Samsung 55" TV',
            days: 3,
          ),
        ).body,
        "Samsung 55\" TV'nin iade süresi 3 gün sonra bitiyor.",
      );
    });

    test('budget 100 %', () {
      expect(
        messageFor(
          reminder(
            ReminderType.budget100,
            category: SpendingCategory.foodDrink,
          ),
        ).body,
        "Yeme-İçme bütçenin %100'üne ulaştın.",
      );
    });

    test('a missing product name still reads well', () {
      expect(
        messageFor(reminder(ReminderType.warrantyExpiry, days: 7)).body,
        'Ürününün garanti süresinin bitmesine 7 gün kaldı.',
      );
    });

    test('a return text starting with i is capitalised the Turkish way', () {
      expect(
        messageFor(
          reminder(ReminderType.returnDeadline, name: 'iPhone 15', days: 1),
        ).body,
        startsWith('İPhone'),
      );
    });
  });

  group('genitive', () {
    const cases = {
      'AirPods': "AirPods'un",
      'ayakkabı': 'ayakkabının',
      'TV': "TV'nin",
      'LG': "LG'nin",
      'Samsung 55" TV': "Samsung 55\" TV'nin",
      'KABLOSUZ KULAKLIK': "KABLOSUZ KULAKLIK'ın",
      'Galaxy S24': "Galaxy S24'ün",
      'iPhone 15': "iPhone 15'in",
      'Dizüstü bilgisayar': "Dizüstü bilgisayar'ın",
      'Ütü': "Ütü'nün",
      'Kamera 360': "Kamera 360'ın",
    };
    cases.forEach((name, expected) {
      test(name, () => expect(genitive(name), expected));
    });
  });

  group('ablative', () {
    const cases = {
      'Trendyol': "Trendyol'dan",
      'MediaMarkt': "MediaMarkt'tan",
      'Teknosa': "Teknosa'dan",
      'Vatan Bilgisayar': "Vatan Bilgisayar'dan",
      'Hepsiburada': "Hepsiburada'dan",
      'Koton': "Koton'dan",
      'Gratis': "Gratis'ten",
      'LC Waikiki': "LC Waikiki'den",
      'IKEA': "IKEA'dan",
    };
    cases.forEach((name, expected) {
      test(name, () => expect(ablative(name), expected));
    });
  });
}
