import 'package:material_ui/material_ui.dart';

import '../theme/app_colors.dart';
import '../theme/app_dimens.dart';
import '../theme/app_text_styles.dart';

/// An error message with an optional "Tekrar dene" button.
class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.message, this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xxl),
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            maxWidth: AppSizes.emptyStateMaxWidth,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Icon(
                Icons.cloud_off_outlined,
                size: AppSizes.iconXl,
                color: AppColors.danger,
              ),
              const SizedBox(height: AppSpacing.l),
              Text(
                message,
                style: AppTextStyles.body,
                textAlign: TextAlign.center,
              ),
              if (onRetry != null) ...[
                const SizedBox(height: AppSpacing.xxl),
                FilledButton(
                  onPressed: onRetry,
                  child: const Text('Tekrar dene'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
