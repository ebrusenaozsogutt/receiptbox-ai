import 'package:material_ui/material_ui.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../domain/installment_models.dart';

/// The dot of one payment: filled = seen on a bank statement, soft = taken as paid, empty = not
/// seen yet.
class PaymentDot extends StatelessWidget {
  const PaymentDot({super.key, required this.status});

  final PaymentStatus status;

  @override
  Widget build(BuildContext context) {
    final (fill, border) = switch (status) {
      PaymentStatus.observed => (AppColors.success, AppColors.success),
      PaymentStatus.inferred => (AppColors.successSoft, AppColors.success),
      PaymentStatus.expected => (AppColors.surface, AppColors.textSubtle),
    };
    return Container(
      key: Key('payment_dot_${status.name}'),
      width: AppSizes.categoryDot,
      height: AppSizes.categoryDot,
      decoration: BoxDecoration(
        color: fill,
        shape: BoxShape.circle,
        border: Border.all(color: border, width: AppSizes.borderWidthStrong),
      ),
    );
  }
}

/// The "TAHMİNİ" pill: a purchase made from a bank row, waiting for its receipt.
class EstimatedBadge extends StatelessWidget {
  const EstimatedBadge({super.key, this.label = 'TAHMİNİ'});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.s,
        vertical: AppSpacing.badgeV,
      ),
      decoration: BoxDecoration(
        color: AppColors.infoSoft,
        borderRadius: AppRadius.circular(AppRadius.pill),
      ),
      child: Text(
        label,
        style: AppTextStyles.overline.copyWith(color: AppColors.info),
      ),
    );
  }
}

/// The "TAKSİT" pill on a bank import row and on a purchase paid in installments.
class InstallmentBadge extends StatelessWidget {
  const InstallmentBadge({super.key, this.label = 'TAKSİT'});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.s,
        vertical: AppSpacing.badgeV,
      ),
      decoration: BoxDecoration(
        color: AppColors.primarySoft,
        borderRadius: AppRadius.circular(AppRadius.pill),
      ),
      child: Text(
        label,
        style: AppTextStyles.overline.copyWith(color: AppColors.primary),
      ),
    );
  }
}
