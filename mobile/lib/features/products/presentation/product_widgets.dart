import 'package:material_ui/material_ui.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';

/// The Figma `Badge` of "01 · Ana Sayfa": İADE (danger) and GARANTİ (warning).
enum DeadlineKind {
  returnWindow('İADE', AppColors.dangerSoft, AppColors.danger),
  warranty('GARANTİ', AppColors.warningSoft, AppColors.warning);

  const DeadlineKind(this.label, this.background, this.foreground);

  final String label;
  final Color background;
  final Color foreground;
}

class DeadlineBadge extends StatelessWidget {
  const DeadlineBadge({super.key, required this.kind});

  final DeadlineKind kind;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.s,
        vertical: AppSpacing.badgeV,
      ),
      decoration: BoxDecoration(
        color: kind.background,
        borderRadius: AppRadius.circular(AppRadius.pill),
      ),
      child: Text(
        kind.label,
        style: AppTextStyles.overline.copyWith(color: kind.foreground),
      ),
    );
  }
}

/// "2 gün", "Bugün", "Süresi doldu".
String daysLeftLabel(int days) {
  if (days < 0) return 'Süresi doldu';
  if (days == 0) return 'Bugün';
  return '$days gün';
}

/// A small pill: a status or a note next to a title.
class InfoPill extends StatelessWidget {
  const InfoPill({
    super.key,
    required this.label,
    required this.background,
    required this.foreground,
  });

  final String label;
  final Color background;
  final Color foreground;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.s,
        vertical: AppSpacing.badgeV,
      ),
      decoration: BoxDecoration(
        color: background,
        borderRadius: AppRadius.circular(AppRadius.pill),
      ),
      child: Text(
        label,
        style: AppTextStyles.overline.copyWith(color: foreground),
      ),
    );
  }
}
