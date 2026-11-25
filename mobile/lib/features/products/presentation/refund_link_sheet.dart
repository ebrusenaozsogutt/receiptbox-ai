import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/utils/date_format.dart';
import '../../../core/utils/money_format.dart';
import '../data/products_api.dart';
import '../domain/product_models.dart';

/// "Bu para iadesi X alışverişine ait olabilir. İade olarak bağlansın mı?" (spec 9): a bank
/// CREDIT row and its candidate purchases. Only a suggestion: nothing happens without an answer.
/// Returns the purchase it was linked to, or null.
Future<String?> askRefundLink({
  required BuildContext context,
  required ProviderContainer container,
  required RefundSuggestion suggestion,
}) async {
  final messenger = ScaffoldMessenger.maybeOf(context);
  final chosen = await showModalBottomSheet<RefundCandidate>(
    context: context,
    useRootNavigator: true,
    isScrollControlled: true,
    builder: (_) => RefundLinkSheet(suggestion: suggestion),
  );
  if (chosen == null) return null;
  try {
    await container
        .read(productsApiProvider)
        .linkRefund(suggestion.observationId, chosen.transactionId);
    return chosen.transactionId;
  } on ApiError catch (error) {
    messenger?.showSnackBar(SnackBar(content: Text(error.message)));
    return null;
  }
}

class RefundLinkSheet extends StatelessWidget {
  const RefundLinkSheet({super.key, required this.suggestion});

  final RefundSuggestion suggestion;

  @override
  Widget build(BuildContext context) {
    final candidates = suggestion.candidates;
    final single = candidates.length == 1;
    return SafeArea(
      child: SingleChildScrollView(
        key: const Key('refund_link_sheet'),
        padding: const EdgeInsets.all(AppSpacing.screenH),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Bu bir iade olabilir mi?', style: AppTextStyles.titleM),
            const SizedBox(height: AppSpacing.s),
            Text(
              single
                  ? 'Bu para iadesi ${candidates.first.merchant} alışverişine ait '
                        'olabilir. İade olarak bağlansın mı?'
                  : 'Bu para iadesi şu alışverişlerden birine ait olabilir. '
                        'Hangisine bağlansın?',
              key: const Key('refund_link_question'),
              style: AppTextStyles.body.copyWith(color: AppColors.textMuted),
            ),
            const SizedBox(height: AppSpacing.m),
            Text(
              '${suggestion.merchant} · ${formatDateTr(suggestion.date)} · '
              '+${formatMoneyTl(suggestion.amountMinor)}',
              style: AppTextStyles.bodyStrong.copyWith(
                color: AppColors.success,
              ),
            ),
            for (final candidate in candidates) ...[
              const SizedBox(height: AppSpacing.s),
              OutlinedButton(
                key: Key('refund_link_${candidate.transactionId}'),
                onPressed: () => Navigator.of(context).pop(candidate),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: AppSpacing.s),
                  child: Column(
                    children: [
                      Text(
                        '${candidate.merchant} · ${formatDateTr(candidate.purchaseDate)}',
                        style: AppTextStyles.bodyStrong,
                      ),
                      Text(
                        '${formatMoneyTl(candidate.totalMinor)} · iade edilebilir '
                        '${formatMoneyTl(candidate.refundableMinor)}',
                        style: AppTextStyles.bodyS,
                      ),
                    ],
                  ),
                ),
              ),
            ],
            const SizedBox(height: AppSpacing.m),
            TextButton(
              key: const Key('refund_link_later'),
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Şimdi değil'),
            ),
          ],
        ),
      ),
    );
  }
}
