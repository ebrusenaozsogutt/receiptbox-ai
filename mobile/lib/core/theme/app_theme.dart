import 'package:material_ui/material_ui.dart';

import 'app_colors.dart';
import 'app_dimens.dart';
import 'app_text_styles.dart';

/// The one ThemeData of the app, built only from the tokens in this folder.
class AppTheme {
  const AppTheme._();

  static ThemeData light() {
    const colorScheme = ColorScheme.light(
      primary: AppColors.primary,
      onPrimary: AppColors.onPrimary,
      primaryContainer: AppColors.primarySoft,
      onPrimaryContainer: AppColors.primary,
      secondary: AppColors.primary,
      onSecondary: AppColors.onPrimary,
      surface: AppColors.surface,
      onSurface: AppColors.text,
      onSurfaceVariant: AppColors.textMuted,
      surfaceContainerHighest: AppColors.surfaceAlt,
      outline: AppColors.border,
      outlineVariant: AppColors.border,
      error: AppColors.danger,
      onError: AppColors.onPrimary,
      errorContainer: AppColors.dangerSoft,
      onErrorContainer: AppColors.danger,
      scrim: AppColors.scrim,
    );

    final inputBorder = OutlineInputBorder(
      borderRadius: AppRadius.control,
      borderSide: const BorderSide(
        color: AppColors.border,
        width: AppSizes.borderWidth,
      ),
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      fontFamily: AppTextStyles.fontFamily,
      scaffoldBackgroundColor: AppColors.bg,
      canvasColor: AppColors.bg,
      textTheme: TextTheme(
        displayLarge: AppTextStyles.display,
        displayMedium: AppTextStyles.display,
        displaySmall: AppTextStyles.display,
        headlineLarge: AppTextStyles.titleL,
        headlineMedium: AppTextStyles.titleL,
        headlineSmall: AppTextStyles.titleL,
        titleLarge: AppTextStyles.titleL,
        titleMedium: AppTextStyles.titleS,
        titleSmall: AppTextStyles.titleS,
        bodyLarge: AppTextStyles.body,
        bodyMedium: AppTextStyles.body,
        bodySmall: AppTextStyles.bodyS,
        labelLarge: AppTextStyles.bodyStrong,
        labelMedium: AppTextStyles.label,
        labelSmall: AppTextStyles.caption,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: AppColors.bg,
        foregroundColor: AppColors.text,
        elevation: AppSpacing.none,
        scrolledUnderElevation: AppSpacing.none,
        centerTitle: false,
        titleTextStyle: AppTextStyles.titleL,
        iconTheme: const IconThemeData(
          color: AppColors.text,
          size: AppSizes.icon,
        ),
      ),
      cardTheme: CardThemeData(
        color: AppColors.surface,
        elevation: AppSpacing.none,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: AppRadius.card,
          side: const BorderSide(
            color: AppColors.border,
            width: AppSizes.borderWidth,
          ),
        ),
      ),
      dividerTheme: const DividerThemeData(
        color: AppColors.border,
        thickness: AppSizes.borderWidth,
        space: AppSizes.borderWidth,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.primary,
          foregroundColor: AppColors.onPrimary,
          disabledBackgroundColor: AppColors.surfaceAlt,
          disabledForegroundColor: AppColors.textSubtle,
          minimumSize: const Size.fromHeight(AppSizes.buttonHeight),
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl),
          shape: const RoundedRectangleBorder(borderRadius: AppRadius.control),
          textStyle: AppTextStyles.bodyStrong,
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          backgroundColor: AppColors.surface,
          foregroundColor: AppColors.primary,
          minimumSize: const Size.fromHeight(AppSizes.buttonHeight),
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl),
          side: const BorderSide(
            color: AppColors.primary,
            width: AppSizes.borderWidthStrong,
          ),
          shape: const RoundedRectangleBorder(borderRadius: AppRadius.control),
          textStyle: AppTextStyles.bodyStrong,
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: AppColors.primary,
          minimumSize: const Size(AppSizes.minTapTarget, AppSizes.buttonHeight),
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl),
          shape: const RoundedRectangleBorder(borderRadius: AppRadius.control),
          textStyle: AppTextStyles.bodyStrong,
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.surface,
        isDense: false,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.inputGap,
          vertical: AppSpacing.m,
        ),
        hintStyle: AppTextStyles.body.copyWith(color: AppColors.textSubtle),
        errorStyle: AppTextStyles.bodyS.copyWith(color: AppColors.danger),
        errorMaxLines: 3,
        border: inputBorder,
        enabledBorder: inputBorder,
        disabledBorder: inputBorder,
        focusedBorder: inputBorder.copyWith(
          borderSide: const BorderSide(
            color: AppColors.primary,
            width: AppSizes.borderWidthStrong,
          ),
        ),
        errorBorder: inputBorder.copyWith(
          borderSide: const BorderSide(
            color: AppColors.danger,
            width: AppSizes.borderWidth,
          ),
        ),
        focusedErrorBorder: inputBorder.copyWith(
          borderSide: const BorderSide(
            color: AppColors.danger,
            width: AppSizes.borderWidthStrong,
          ),
        ),
      ),
      checkboxTheme: CheckboxThemeData(
        shape: RoundedRectangleBorder(
          borderRadius: AppRadius.circular(AppRadius.xs),
        ),
        side: const BorderSide(
          color: AppColors.textSubtle,
          width: AppSizes.borderWidthStrong,
        ),
        fillColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected)
              ? AppColors.primary
              : AppColors.surface,
        ),
        checkColor: const WidgetStatePropertyAll(AppColors.onPrimary),
      ),
      switchTheme: SwitchThemeData(
        thumbColor: const WidgetStatePropertyAll(AppColors.surface),
        trackColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected)
              ? AppColors.primary
              : AppColors.textSubtle,
        ),
        trackOutlineColor: const WidgetStatePropertyAll(AppColors.surface),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: AppColors.surface,
        surfaceTintColor: AppColors.surface,
        showDragHandle: true,
        modalBackgroundColor: AppColors.surface,
        shape: RoundedRectangleBorder(borderRadius: AppRadius.sheetTop),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: AppColors.surface,
        surfaceTintColor: AppColors.surface,
        shape: RoundedRectangleBorder(borderRadius: AppRadius.card),
        titleTextStyle: AppTextStyles.titleM,
        contentTextStyle: AppTextStyles.body.copyWith(
          color: AppColors.textMuted,
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: AppColors.text,
        contentTextStyle: AppTextStyles.body.copyWith(
          color: AppColors.onPrimary,
        ),
        shape: const RoundedRectangleBorder(borderRadius: AppRadius.control),
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: AppColors.primary,
        strokeWidth: AppSizes.progressThickness,
      ),
      listTileTheme: ListTileThemeData(
        iconColor: AppColors.textMuted,
        textColor: AppColors.text,
        titleTextStyle: AppTextStyles.bodyStrong,
        subtitleTextStyle: AppTextStyles.bodyS.copyWith(
          color: AppColors.textMuted,
        ),
        minTileHeight: AppSizes.minTapTarget,
      ),
    );
  }
}
