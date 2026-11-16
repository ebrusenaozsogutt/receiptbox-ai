import 'package:flutter/services.dart' show FontLoader, rootBundle;
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/core/theme/app_colors.dart';
import 'package:receiptbox/core/theme/app_dimens.dart';
import 'package:receiptbox/core/theme/app_text_styles.dart';
import 'package:receiptbox/core/theme/app_theme.dart';

/// The tokens must equal the "Direction v1" values of docs/design/DESIGN_TRACK.md / Figma.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('colors (Figma variables)', () {
    final expected = <String, (Color, int)>{
      'primary': (AppColors.primary, 0xFF0E5E57),
      'primary-soft': (AppColors.primarySoft, 0xFFE3F1EE),
      'on-primary': (AppColors.onPrimary, 0xFFFFFFFF),
      'bg': (AppColors.bg, 0xFFF5F7F6),
      'surface': (AppColors.surface, 0xFFFFFFFF),
      'surface-alt': (AppColors.surfaceAlt, 0xFFEEF2F1),
      'border': (AppColors.border, 0xFFE1E7E5),
      'text': (AppColors.text, 0xFF16211F),
      'text-muted': (AppColors.textMuted, 0xFF5E6B68),
      'text-subtle': (AppColors.textSubtle, 0xFF8A9693),
      'success': (AppColors.success, 0xFF047857),
      'success-soft': (AppColors.successSoft, 0xFFD9F3E8),
      'warning': (AppColors.warning, 0xFFB45309),
      'warning-soft': (AppColors.warningSoft, 0xFFFDF0D5),
      'danger': (AppColors.danger, 0xFFB42318),
      'danger-soft': (AppColors.dangerSoft, 0xFFFDE4E1),
      'info': (AppColors.info, 0xFF2457C5),
      'info-soft': (AppColors.infoSoft, 0xFFE1EAFB),
      'cat/grocery': (AppColors.catGrocery, 0xFF2F9E6E),
      'cat/tech': (AppColors.catTech, 0xFF3B6FD8),
      'cat/food': (AppColors.catFood, 0xFFE08A2E),
      'cat/transport': (AppColors.catTransport, 0xFF8A5CD6),
      'cat/clothing': (AppColors.catClothing, 0xFFD64F7A),
      'cat/subscription': (AppColors.catSubscription, 0xFF2AA3B8),
    };
    for (final entry in expected.entries) {
      test('color/${entry.key}', () {
        expect(entry.value.$1.toARGB32(), entry.value.$2);
      });
    }
  });

  group('type scale: size / line height / weight', () {
    final expected = <String, (TextStyle, double, double, int)>{
      'Display 32/40 ExtraBold': (AppTextStyles.display, 32, 40, 800),
      'Title L 22/28 Bold': (AppTextStyles.titleL, 22, 28, 700),
      'Title M 18/24 Bold': (AppTextStyles.titleM, 18, 24, 700),
      'Title S 16/22 SemiBold': (AppTextStyles.titleS, 16, 22, 600),
      'Body 15/22 Regular': (AppTextStyles.body, 15, 22, 400),
      'Body strong 15/22 SemiBold': (AppTextStyles.bodyStrong, 15, 22, 600),
      'Body S 13/18 Regular': (AppTextStyles.bodyS, 13, 18, 400),
      'Label 13/16 SemiBold': (AppTextStyles.label, 13, 16, 600),
      'Caption 12/16 Medium': (AppTextStyles.caption, 12, 16, 500),
      'Overline 11/14 Bold': (AppTextStyles.overline, 11, 14, 700),
    };
    for (final entry in expected.entries) {
      test(entry.key, () {
        final (style, size, lineHeight, weight) = entry.value;

        expect(style.fontFamily, 'PlusJakartaSans');
        expect(style.fontSize, size);
        expect(style.height! * style.fontSize!, closeTo(lineHeight, 0.001));
        expect(style.fontWeight!.value, weight);
        expect(style.fontVariations!.single.axis, 'wght');
        expect(style.fontVariations!.single.value, weight.toDouble());
      });
    }

    test('Overline has +8% letter spacing', () {
      expect(AppTextStyles.overline.letterSpacing, closeTo(11 * 0.08, 0.001));
    });
  });

  group('radii and sizes', () {
    test('radii 8 / 12 / 16 / 24', () {
      expect(
        [AppRadius.s, AppRadius.m, AppRadius.l, AppRadius.xl],
        [8, 12, 16, 24],
      );
    });

    test('component sizes from Figma', () {
      expect(AppSizes.buttonHeight, 48);
      expect(AppSizes.inputHeight, 48);
      expect(AppSizes.navHeight, 76);
      expect(AppSizes.navAddButton, 56);
      expect(AppRadius.navAddButton, 18);
      expect(AppSizes.minTapTarget, 48);
    });
  });

  group('ThemeData is built from the tokens', () {
    final theme = AppTheme.light();

    test('colors', () {
      expect(theme.scaffoldBackgroundColor, AppColors.bg);
      expect(theme.colorScheme.primary, AppColors.primary);
      expect(theme.colorScheme.onPrimary, AppColors.onPrimary);
      expect(theme.colorScheme.surface, AppColors.surface);
      expect(theme.colorScheme.error, AppColors.danger);
      expect(theme.cardTheme.color, AppColors.surface);
    });

    test('font', () {
      expect(theme.textTheme.bodyMedium!.fontFamily, 'PlusJakartaSans');
      expect(theme.textTheme.titleLarge!.fontSize, 22);
    });
  });

  group('buttons and inputs match the Figma components', () {
    setUpAll(() async {
      final loader = FontLoader('PlusJakartaSans')
        ..addFont(rootBundle.load('assets/fonts/PlusJakartaSans-Variable.ttf'));
      await loader.load();
    });

    Future<void> pump(WidgetTester tester, Widget child) {
      return tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: Scaffold(
            body: Padding(
              padding: const EdgeInsets.all(AppSpacing.l),
              child: child,
            ),
          ),
        ),
      );
    }

    testWidgets('primary button: 48 high, radius 12, teal, white label', (
      tester,
    ) async {
      await pump(
        tester,
        FilledButton(onPressed: () {}, child: const Text('Kaydet')),
      );

      expect(tester.getSize(find.byType(FilledButton)).height, 48);
      final material = tester.widget<Material>(
        find.descendant(
          of: find.byType(FilledButton),
          matching: find.byType(Material),
        ),
      );
      expect(material.color, AppColors.primary);
      expect(material.shape, isA<RoundedRectangleBorder>());
      expect(
        (material.shape! as RoundedRectangleBorder).borderRadius,
        BorderRadius.circular(12),
      );
      final labelStyle = AppTheme.light().filledButtonTheme.style!.textStyle!
          .resolve({})!;
      expect(labelStyle.fontSize, 15); // Body/M Strong 15/22 SemiBold
      expect(labelStyle.fontWeight, FontWeight.w600);
      expect(
        AppTheme.light().filledButtonTheme.style!.foregroundColor!.resolve({}),
        AppColors.onPrimary,
      );
    });

    testWidgets('secondary button: white with a 1.5 teal border', (
      tester,
    ) async {
      await pump(
        tester,
        OutlinedButton(onPressed: () {}, child: const Text('Çıkış yap')),
      );

      expect(tester.getSize(find.byType(OutlinedButton)).height, 48);
      final style = tester
          .widget<OutlinedButton>(find.byType(OutlinedButton))
          .style;
      final theme = AppTheme.light().outlinedButtonTheme.style!;
      expect(style, isNull); // the look comes from the theme alone
      expect(theme.side!.resolve({})!.width, 1.5);
      expect(theme.side!.resolve({})!.color, AppColors.primary);
    });

    testWidgets('text field: 48 high with a 1 px border and radius 12', (
      tester,
    ) async {
      await pump(tester, const TextField());

      expect(tester.getSize(find.byType(TextField)).height, closeTo(48, 1));
      final decoration = AppTheme.light().inputDecorationTheme;
      final border = decoration.enabledBorder! as OutlineInputBorder;
      expect(border.borderSide.color, AppColors.border);
      expect(border.borderSide.width, 1);
      expect(border.borderRadius, BorderRadius.circular(12));
      expect(decoration.fillColor, AppColors.surface);
    });
  });
}
