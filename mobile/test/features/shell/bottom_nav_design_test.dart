import 'package:flutter/services.dart' show FontLoader, rootBundle;
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/core/theme/app_colors.dart';
import 'package:receiptbox/core/theme/app_dimens.dart';
import 'package:receiptbox/core/theme/app_theme.dart';
import 'package:receiptbox/features/shell/presentation/bottom_nav.dart';

/// The bottom navigation must match the Figma component "BottomNav" (node 2:22):
/// 76 high, top border, 20 side padding, 24 icons, caption labels, and a raised 56x56
/// rounded-square (+) button with radius 18 and a teal shadow.
Future<({List<int> tabTaps, List<bool> addTaps})> _pump(
  WidgetTester tester, {
  int selected = 0,
}) async {
  final tabTaps = <int>[];
  final addTaps = <bool>[];
  tester.view.physicalSize = const Size(
    1236,
    2400,
  ); // 412 x 800 logical pixels at 3x
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);

  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(
        bottomNavigationBar: AppBottomNav(
          selectedIndex: selected,
          onTabSelected: tabTaps.add,
          onAddPressed: () => addTaps.add(true),
        ),
      ),
    ),
  );
  return (tabTaps: tabTaps, addTaps: addTaps);
}

Color? _labelColor(WidgetTester tester, String label) =>
    tester.widget<Text>(find.text(label)).style?.color;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // Use the real app font. (Tests otherwise draw text with the very wide "Ahem" test font,
  // which would make the label widths, and so the layout, unlike the real app.)
  setUpAll(() async {
    final loader = FontLoader('PlusJakartaSans')
      ..addFont(rootBundle.load('assets/fonts/PlusJakartaSans-Variable.ttf'));
    await loader.load();
  });

  testWidgets('the bar is 76 high and 412 wide on a 412 dp screen', (
    tester,
  ) async {
    await _pump(tester);

    final size = tester.getSize(find.byType(AppBottomNav));

    expect(size.height, 76);
    expect(size.height, AppSizes.navHeight);
    expect(size.width, 412);
  });

  testWidgets('the surface is white with a 1 px border on top', (tester) async {
    await _pump(tester);

    final box = tester.widget<DecoratedBox>(
      find
          .descendant(
            of: find.byType(AppBottomNav),
            matching: find.byType(DecoratedBox),
          )
          .first,
    );
    final decoration = box.decoration as BoxDecoration;
    final border = decoration.border! as Border;

    expect(decoration.color, AppColors.surface);
    expect(border.top.color, AppColors.border);
    expect(border.top.width, 1);
    expect(border.bottom.style, BorderStyle.none);
  });

  group('the raised (+) button', () {
    testWidgets('is 56 x 56', (tester) async {
      await _pump(tester);

      expect(
        tester.getSize(find.byKey(const Key('nav_add_button'))),
        const Size(56, 56),
      );
    });

    testWidgets('is a rounded square (radius 18), not a circle', (
      tester,
    ) async {
      await _pump(tester);

      final ink = tester.widget<InkWell>(
        find.byKey(const Key('nav_add_button')),
      );

      expect(ink.borderRadius, BorderRadius.circular(18));
    });

    testWidgets('is primary teal with the soft shadow 0 6 14', (tester) async {
      await _pump(tester);

      final box = tester.widget<DecoratedBox>(
        find
            .ancestor(
              of: find.byKey(const Key('nav_add_button')),
              matching: find.byType(DecoratedBox),
            )
            .first,
      );
      final decoration = box.decoration as BoxDecoration;
      final shadow = decoration.boxShadow!.single;

      expect(decoration.color, AppColors.primary);
      expect(decoration.color, const Color(0xFF0E5E57));
      expect(decoration.borderRadius, BorderRadius.circular(18));
      expect(shadow.offset, const Offset(0, 6));
      expect(shadow.blurRadius, 14);
      expect(
        shadow.color.toARGB32(),
        0x4D0D5E57,
      ); // rgb(13, 94, 87) at 30% opacity
      expect(shadow.color.a, closeTo(0.30, 0.005));
    });

    testWidgets('sits in the middle of the bar', (tester) async {
      await _pump(tester);

      final center = tester.getCenter(find.byKey(const Key('nav_add_button')));
      final bar = tester.getRect(find.byType(AppBottomNav));

      expect(center.dy, closeTo(bar.center.dy, 0.5));
      // In Figma the tabs keep their natural width and are spread evenly, so the (+) sits a
      // little right of the screen's center: its center is at about x = 226 of 412.
      expect(center.dx, closeTo(226, 12));
    });

    testWidgets('calls onAddPressed when tapped', (tester) async {
      final taps = await _pump(tester);

      await tester.tap(find.byKey(const Key('nav_add_button')));

      expect(taps.addTaps, [true]);
      expect(taps.tabTaps, isEmpty);
    });
  });

  group('robustness', () {
    for (final entry in {
      'a narrow 320 dp phone': (const Size(960, 2400), 1.0),
      'a narrow phone with a very large system font': (
        const Size(960, 2400),
        2.0,
      ),
      'a normal phone with a large system font': (const Size(1236, 2400), 1.5),
    }.entries) {
      testWidgets('does not overflow on ${entry.key}', (tester) async {
        tester.view.physicalSize = entry.value.$1;
        tester.view.devicePixelRatio = 3;
        addTearDown(tester.view.reset);

        await tester.pumpWidget(
          MaterialApp(
            theme: AppTheme.light(),
            home: MediaQuery(
              data: MediaQueryData(
                size: Size(entry.value.$1.width / 3, 800),
                textScaler: TextScaler.linear(entry.value.$2),
              ),
              child: Scaffold(
                bottomNavigationBar: AppBottomNav(
                  selectedIndex: 0,
                  onTabSelected: (_) {},
                  onAddPressed: () {},
                ),
              ),
            ),
          ),
        );

        expect(tester.takeException(), isNull);
        expect(
          tester.getSize(find.byKey(const Key('nav_add_button'))),
          const Size(56, 56),
        );
      });
    }
  });

  group('tabs', () {
    testWidgets('labels use the Caption style 12/16 Medium', (tester) async {
      await _pump(tester);

      for (final label in ['Ana Sayfa', 'Harcamalar', 'Ürünler', 'Asistan']) {
        final style = tester.widget<Text>(find.text(label)).style!;
        expect(style.fontSize, 12, reason: label);
        expect(style.height, closeTo(16 / 12, 0.001), reason: label);
        expect(style.fontWeight, FontWeight.w500, reason: label);
      }
    });

    testWidgets('the selected tab is primary, the others are text-subtle', (
      tester,
    ) async {
      await _pump(tester, selected: 1);

      expect(_labelColor(tester, 'Harcamalar'), AppColors.primary);
      expect(_labelColor(tester, 'Ana Sayfa'), AppColors.textSubtle);
      expect(_labelColor(tester, 'Ürünler'), AppColors.textSubtle);
      expect(_labelColor(tester, 'Asistan'), AppColors.textSubtle);
      expect(AppColors.textSubtle, const Color(0xFF8A9693));
    });

    testWidgets(
      'are laid out left to right: Ana Sayfa, Harcamalar, (+), Ürünler, Asistan',
      (tester) async {
        await _pump(tester);

        final xs = [
          tester.getCenter(find.text('Ana Sayfa')).dx,
          tester.getCenter(find.text('Harcamalar')).dx,
          tester.getCenter(find.byKey(const Key('nav_add_button'))).dx,
          tester.getCenter(find.text('Ürünler')).dx,
          tester.getCenter(find.text('Asistan')).dx,
        ];
        expect([...xs]..sort(), xs);
      },
    );

    testWidgets(
      'the content starts 20 from the left and ends 20 from the right',
      (tester) async {
        await _pump(tester);

        final first = tester.getRect(find.text('Ana Sayfa'));
        final last = tester.getRect(find.text('Asistan'));

        // Labels are narrower than their tab: allow the tab's min-width slack.
        expect(first.left, greaterThanOrEqualTo(20));
        expect(first.left, lessThan(32));
        expect(412 - last.right, greaterThanOrEqualTo(20));
        expect(412 - last.right, lessThan(32));
      },
    );

    testWidgets('every tab is at least 48 x 48 to tap', (tester) async {
      await _pump(tester);

      for (final label in ['Ana Sayfa', 'Harcamalar', 'Ürünler', 'Asistan']) {
        final target = tester.getSize(
          find
              .ancestor(
                of: find.text(label),
                matching: find.byType(ConstrainedBox),
              )
              .first,
        );
        expect(target.width, greaterThanOrEqualTo(48), reason: label);
        expect(target.height, greaterThanOrEqualTo(48), reason: label);
      }
      expect(
        tester.getSize(find.byKey(const Key('nav_add_button'))).shortestSide,
        56,
      );
    });

    testWidgets('report the tapped tab index (the + is not a tab)', (
      tester,
    ) async {
      final taps = await _pump(tester);

      await tester.tap(find.text('Ana Sayfa'));
      await tester.tap(find.text('Harcamalar'));
      await tester.tap(find.text('Ürünler'));
      await tester.tap(find.text('Asistan'));

      expect(taps.tabTaps, [0, 1, 2, 3]);
    });

    testWidgets('are announced as selectable buttons to screen readers', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await _pump(tester, selected: 2);

      expect(
        tester.getSemantics(find.text('Ürünler')),
        matchesSemantics(
          label: 'Ürünler',
          isButton: true,
          isSelected: true,
          hasTapAction: true,
          hasSelectedState: true,
        ),
      );
      expect(find.bySemanticsLabel('Ekle'), findsOneWidget);
      handle.dispose();
    });
  });
}
