import 'package:material_ui/material_ui.dart';

import '../theme/app_colors.dart';
import '../theme/app_dimens.dart';
import '../theme/app_text_styles.dart';

enum MessageBannerKind { error, info }

/// A short message in a tinted box, e.g. "E-posta veya parola hatalı."
class MessageBanner extends StatelessWidget {
  const MessageBanner(
    this.message, {
    super.key,
    this.kind = MessageBannerKind.error,
  });

  final String message;
  final MessageBannerKind kind;

  @override
  Widget build(BuildContext context) {
    final isError = kind == MessageBannerKind.error;
    final foreground = isError ? AppColors.danger : AppColors.info;
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.m),
        decoration: BoxDecoration(
          color: isError ? AppColors.dangerSoft : AppColors.infoSoft,
          borderRadius: AppRadius.control,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              isError ? Icons.error_outline : Icons.info_outline,
              size: AppSizes.iconS,
              color: foreground,
            ),
            const SizedBox(width: AppSpacing.s),
            Expanded(
              child: Text(
                message,
                style: AppTextStyles.bodyS.copyWith(color: foreground),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
