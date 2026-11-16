import 'package:material_ui/material_ui.dart';

import '../theme/app_colors.dart';
import '../theme/app_dimens.dart';
import '../theme/app_text_styles.dart';

/// A centered progress indicator with an optional message.
class LoadingView extends StatelessWidget {
  const LoadingView({super.key, this.message});

  final String? message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(
            width: AppSizes.progressSize,
            height: AppSizes.progressSize,
            child: CircularProgressIndicator(),
          ),
          if (message != null) ...[
            const SizedBox(height: AppSpacing.l),
            Text(
              message!,
              style: AppTextStyles.body.copyWith(color: AppColors.textMuted),
            ),
          ],
        ],
      ),
    );
  }
}
