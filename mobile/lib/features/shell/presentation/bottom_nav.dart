import 'package:flutter_svg/flutter_svg.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';

/// The bottom navigation, built from the Figma component "BottomNav" (node 2:22):
/// Ana Sayfa · Harcamalar · (+) · Ürünler · Asistan, with the (+) as a raised rounded square.
///
/// [selectedIndex] counts the four tabs only (0 Ana Sayfa, 1 Harcamalar, 2 Ürünler,
/// 3 Asistan); the (+) is an action, not a tab.
class AppBottomNav extends StatelessWidget {
  const AppBottomNav({
    super.key,
    required this.selectedIndex,
    required this.onTabSelected,
    required this.onAddPressed,
  });

  final int selectedIndex;
  final ValueChanged<int> onTabSelected;
  final VoidCallback onAddPressed;

  static const _tabs = [
    _TabSpec('Ana Sayfa', 'assets/icons/nav_home.svg'),
    _TabSpec('Harcamalar', 'assets/icons/nav_receipt.svg'),
    _TabSpec('Ürünler', 'assets/icons/nav_box.svg'),
    _TabSpec('Asistan', 'assets/icons/nav_spark.svg'),
  ];

  Widget _tab(int index) => _NavTab(
    spec: _tabs[index],
    selected: index == selectedIndex,
    onTap: () => onTabSelected(index),
  );

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border: Border(
          top: BorderSide(color: AppColors.border, width: AppSizes.borderWidth),
        ),
      ),
      // SafeArea adds the phone's gesture-bar inset below the 76-px bar.
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: AppSizes.navHeight,
          child: Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSizes.navHorizontalPadding,
            ),
            // Tabs are Flexible: with their natural width they are spread out as in Figma,
            // but on a narrow phone or with a large system font they shrink (the label gets
            // an ellipsis) instead of overflowing the bar.
            child: MediaQuery.withClampedTextScaling(
              maxScaleFactor: AppSizes.navMaxTextScale,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Flexible(child: _tab(0)),
                  Flexible(child: _tab(1)),
                  _AddButton(onPressed: onAddPressed),
                  Flexible(child: _tab(2)),
                  Flexible(child: _tab(3)),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _TabSpec {
  const _TabSpec(this.label, this.asset);
  final String label;
  final String asset;
}

class _NavTab extends StatelessWidget {
  const _NavTab({
    required this.spec,
    required this.selected,
    required this.onTap,
  });

  final _TabSpec spec;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected ? AppColors.primary : AppColors.textSubtle;
    return Semantics(
      button: true,
      selected: selected,
      label: spec.label,
      onTap: onTap, // excludeSemantics hides the InkResponse's own action, so repeat it
      excludeSemantics: true,
      child: InkResponse(
        onTap: onTap,
        // The whole bar height is tappable: far above the 48 dp minimum.
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            minWidth: AppSizes.navTabMinWidth,
            minHeight: AppSizes.navHeight,
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              SvgPicture.asset(
                spec.asset,
                width: AppSizes.icon,
                height: AppSizes.icon,
                colorFilter: ColorFilter.mode(color, BlendMode.srcIn),
              ),
              const SizedBox(height: AppSizes.navTabGap),
              Text(
                spec.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: AppTextStyles.caption.copyWith(color: color),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AddButton extends StatelessWidget {
  const _AddButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final radius = AppRadius.circular(AppRadius.navAddButton);
    return Semantics(
      button: true,
      label: 'Ekle',
      onTap: onPressed,
      excludeSemantics: true,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.primary,
          borderRadius: radius,
          boxShadow: AppShadows.navAddButton,
        ),
        child: Material(
          type: MaterialType.transparency,
          child: InkWell(
            key: const Key('nav_add_button'),
            borderRadius: radius,
            onTap: onPressed,
            child: SizedBox(
              width: AppSizes.navAddButton,
              height: AppSizes.navAddButton,
              child: Center(
                child: SvgPicture.asset(
                  'assets/icons/nav_plus.svg',
                  width: AppSizes.iconAdd,
                  height: AppSizes.iconAdd,
                  colorFilter: const ColorFilter.mode(
                    AppColors.onPrimary,
                    BlendMode.srcIn,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
