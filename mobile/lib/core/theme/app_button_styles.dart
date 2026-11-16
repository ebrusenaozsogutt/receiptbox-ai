import 'package:material_ui/material_ui.dart';

import 'app_colors.dart';

/// Button variants that are not part of the default ThemeData.
class AppButtonStyles {
  const AppButtonStyles._();

  /// A filled red button for destructive confirmations ("Hesabı sil").
  static ButtonStyle danger() => FilledButton.styleFrom(
    backgroundColor: AppColors.danger,
    foregroundColor: AppColors.onPrimary,
  );

  /// A text button in red ("Hesabı sil" in Settings).
  static ButtonStyle dangerText() =>
      TextButton.styleFrom(foregroundColor: AppColors.danger);
}
