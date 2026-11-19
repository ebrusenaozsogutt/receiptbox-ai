import 'package:material_ui/material_ui.dart';

import '../theme/app_colors.dart';
import '../theme/app_dimens.dart';
import '../theme/app_text_styles.dart';

/// The "KONTROL ET" pill of the Figma `Badge` component: a field the app is not sure about.
class ReviewBadge extends StatelessWidget {
  const ReviewBadge({super.key, this.label = 'KONTROL ET'});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.s,
        vertical: AppSpacing.badgeV,
      ),
      decoration: BoxDecoration(
        color: AppColors.warningSoft,
        borderRadius: AppRadius.circular(AppRadius.pill),
      ),
      child: Text(
        label,
        style: AppTextStyles.overline.copyWith(color: AppColors.warning),
      ),
    );
  }
}
