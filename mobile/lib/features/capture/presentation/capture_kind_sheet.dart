import 'package:material_ui/material_ui.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../domain/capture_payload.dart';

/// Gallery and shared files can be a receipt or a bank screenshot: ask which one.
/// Returns null when the user closes the sheet.
Future<CaptureKind?> askCaptureKind(BuildContext context) {
  return showModalBottomSheet<CaptureKind>(
    context: context,
    useRootNavigator: true,
    isScrollControlled: true,
    builder: (sheetContext) => SafeArea(
      child: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.screenH,
            AppSpacing.none,
            AppSpacing.screenH,
            AppSpacing.l,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Bu bir ne?', style: AppTextStyles.titleM),
              const SizedBox(height: AppSpacing.s),
              _KindTile(
                key: const Key('kind_receipt'),
                kind: CaptureKind.receipt,
                icon: Icons.receipt_long_outlined,
                title: 'Fiş veya fatura',
                subtitle: 'Market fişi, e-arşiv fatura, e-Fatura PDF',
              ),
              _KindTile(
                key: const Key('kind_bank'),
                kind: CaptureKind.bankScreenshot,
                icon: Icons.account_balance_outlined,
                title: 'Banka ekran görüntüsü',
                subtitle: 'Banka uygulamasındaki harcama listesi',
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

class _KindTile extends StatelessWidget {
  const _KindTile({
    super.key,
    required this.kind,
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final CaptureKind kind;
  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: Container(
        width: AppSizes.iconButton,
        height: AppSizes.iconButton,
        decoration: BoxDecoration(
          color: AppColors.primarySoft,
          borderRadius: AppRadius.circular(AppRadius.m),
        ),
        child: Icon(icon, color: AppColors.primary, size: AppSizes.icon),
      ),
      title: Text(title),
      subtitle: Text(subtitle),
      onTap: () => Navigator.of(context).pop(kind),
    );
  }
}
