import 'dart:ui' show Color;

/// Design tokens: colors. "Direction v1", copied from the Figma variables collection
/// "ReceiptBox Tokens" (docs/design/DESIGN_TRACK.md).
///
/// This folder (core/theme/) is the ONLY place where colors, font sizes, spacing and other sizes
/// are written down. Everything else uses these tokens, so the design can change in one place.
/// `test/theme_tokens_guard_test.dart` fails if a hard-coded value appears elsewhere.
class AppColors {
  const AppColors._();

  // Brand
  static const Color primary = Color(0xFF0E5E57);
  static const Color primarySoft = Color(0xFFE3F1EE);
  static const Color onPrimary = Color(0xFFFFFFFF);

  // Surfaces
  static const Color bg = Color(0xFFF5F7F6);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color surfaceAlt = Color(0xFFEEF2F1);
  static const Color border = Color(0xFFE1E7E5);

  // Text
  static const Color text = Color(0xFF16211F);
  static const Color textMuted = Color(0xFF5E6B68);
  static const Color textSubtle = Color(0xFF8A9693);

  // Status (solid / soft background)
  static const Color success = Color(0xFF047857);
  static const Color successSoft = Color(0xFFD9F3E8);
  static const Color warning = Color(0xFFB45309);
  static const Color warningSoft = Color(0xFFFDF0D5);
  static const Color danger = Color(0xFFB42318);
  static const Color dangerSoft = Color(0xFFFDE4E1);
  static const Color info = Color(0xFF2457C5);
  static const Color infoSoft = Color(0xFFE1EAFB);

  // Category colors. Figma defines only these so far; the other categories (fuel, home, health,
  // entertainment, education, bills) get their colors when the design track delivers them.
  static const Color catGrocery = Color(0xFF2F9E6E);
  static const Color catTech = Color(0xFF3B6FD8);
  static const Color catFood = Color(0xFFE08A2E);
  static const Color catTransport = Color(0xFF8A5CD6);
  static const Color catClothing = Color(0xFFD64F7A);
  static const Color catSubscription = Color(0xFF2AA3B8);
  static const Color catOther = Color(0xFF8A9693);

  // PROVISIONAL: these six categories have no color in Figma yet (docs/design/DESIGN_TRACK.md).
  // Replace them with the designed values when the design track delivers them.
  static const Color catFuel = Color(0xFF9A6B2F);
  static const Color catHome = Color(0xFF6E8B3D);
  static const Color catHealth = Color(0xFFB4527F);
  static const Color catEntertainment = Color(0xFFE0B22E);
  static const Color catEducation = Color(0xFF5B63D3);
  static const Color catBills = Color(0xFF6B7A90);

  /// Shadow tint of the raised (+) button: rgba(13, 94, 87, 0.30) in Figma.
  static const Color primaryShadow = Color(0x4D0D5E57);

  /// Shadow of the selected segment in segmented controls: rgba(0, 0, 0, 0.08).
  static const Color subtleShadow = Color(0x14000000);

  /// Dim layer behind modal sheets and dialogs.
  /// The change chip on the dark spending card (Figma "01 · Ana Sayfa", white at 16 %).
  static const Color heroChip = Color(0x29FFFFFF);

  static const Color scrim = Color(0x8016211F);

  /// Background of the camera screen (the preview is letter-boxed on it) and the shutter ring.
  static const Color cameraBackground = Color(0xFF000000);
  static const Color cameraForeground = Color(0xFFFFFFFF);
}
