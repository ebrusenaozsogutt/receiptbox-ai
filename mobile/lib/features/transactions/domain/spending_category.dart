import 'dart:ui' show Color;

import '../../../core/theme/app_colors.dart';

/// The fixed 13 categories (spec 5.7): backend key, Turkish label, color.
enum SpendingCategory {
  grocery('GROCERY', 'Market', AppColors.catGrocery),
  foodDrink('FOOD_DRINK', 'Yeme-İçme', AppColors.catFood),
  transport('TRANSPORT', 'Ulaşım', AppColors.catTransport),
  fuel('FUEL', 'Yakıt', AppColors.catFuel),
  clothing('CLOTHING', 'Giyim', AppColors.catClothing),
  technology('TECHNOLOGY', 'Teknoloji', AppColors.catTech),
  home('HOME', 'Ev & Yaşam', AppColors.catHome),
  healthCare('HEALTH_CARE', 'Sağlık & Kişisel Bakım', AppColors.catHealth),
  entertainment('ENTERTAINMENT', 'Eğlence', AppColors.catEntertainment),
  subscription('SUBSCRIPTION', 'Abonelik', AppColors.catSubscription),
  education('EDUCATION', 'Eğitim', AppColors.catEducation),
  bills('BILLS', 'Fatura & Hizmetler', AppColors.catBills),
  other('OTHER', 'Diğer', AppColors.catOther);

  const SpendingCategory(this.key, this.label, this.color);

  /// The value the backend uses.
  final String key;
  final String label;
  final Color color;

  static SpendingCategory? fromKey(String? key) {
    for (final category in values) {
      if (category.key == key) return category;
    }
    return null;
  }
}

/// Where the purchase was made (Figma "Nereden alındı?").
enum PurchaseChannel {
  inStore('IN_STORE', 'Mağazada'),
  online('ONLINE', 'Online'),
  unknown('UNKNOWN', 'Belirtilmedi');

  const PurchaseChannel(this.key, this.label);

  final String key;
  final String label;

  static PurchaseChannel fromKey(String? key) {
    for (final channel in values) {
      if (channel.key == key) return channel;
    }
    return PurchaseChannel.unknown;
  }
}
