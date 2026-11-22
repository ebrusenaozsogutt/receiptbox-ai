import 'package:material_ui/material_ui.dart';

import '../theme/app_colors.dart';
import '../theme/app_dimens.dart';
import '../theme/app_text_styles.dart';

enum MatchBadgeKind {
  /// "Eşleşti": the record is, with high certainty, the same purchase as one already saved.
  matched,

  /// "Olası eşleşme": it may be; the user is asked.
  possible,
}

/// The "Eşleşti" / "Olası eşleşme" pill (same shape as the Figma `Badge`, like [ReviewBadge]).
/// There is no Figma frame for it yet: it uses the success and info tokens.
class MatchBadge extends StatelessWidget {
  const MatchBadge({super.key, required this.kind});

  final MatchBadgeKind kind;

  @override
  Widget build(BuildContext context) {
    final matched = kind == MatchBadgeKind.matched;
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.s,
        vertical: AppSpacing.badgeV,
      ),
      decoration: BoxDecoration(
        color: matched ? AppColors.successSoft : AppColors.infoSoft,
        borderRadius: AppRadius.circular(AppRadius.pill),
      ),
      child: Text(
        matched ? 'Eşleşti' : 'Olası eşleşme',
        style: AppTextStyles.overline.copyWith(
          color: matched ? AppColors.success : AppColors.info,
        ),
      ),
    );
  }
}
