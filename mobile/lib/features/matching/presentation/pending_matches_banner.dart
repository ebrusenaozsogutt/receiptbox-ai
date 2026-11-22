import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../transactions/data/transactions_providers.dart';
import '../data/matching_providers.dart';
import '../domain/match_models.dart';
import 'match_sheet.dart';

/// "N eşleşme önerisi bekliyor": shown above the purchase list while a record waits for the
/// user's answer ("Birleştirilsin mi?"). Tapping it opens the question.
class PendingMatchesBanner extends ConsumerWidget {
  const PendingMatchesBanner({super.key});

  Future<void> _open(
    BuildContext context,
    WidgetRef ref,
    List<MatchSuggestion> group,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    final answer = await showMatchSheet(context, group);
    if (answer == null) return;
    ref
      ..invalidate(purchaseListProvider)
      ..invalidate(pendingMatchesProvider);
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          answer.merged
              ? 'Birleştirildi.'
              : 'Ayrı bir harcama olarak kaydedildi.',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final pending = ref.watch(pendingMatchesProvider).value ?? const [];
    if (pending.isEmpty) return const SizedBox.shrink();
    final groups = groupByObservation(pending).values.toList();
    return Padding(
      padding: const EdgeInsets.only(
        left: AppSpacing.screenH,
        right: AppSpacing.screenH,
        bottom: AppSpacing.s,
      ),
      child: Material(
        color: AppColors.infoSoft,
        borderRadius: AppRadius.control,
        child: InkWell(
          key: const Key('pending_matches_banner'),
          borderRadius: AppRadius.control,
          onTap: () => _open(context, ref, groups.first),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.m),
            child: Row(
              children: [
                const Icon(
                  Icons.merge_type,
                  size: AppSizes.iconS,
                  color: AppColors.info,
                ),
                const SizedBox(width: AppSpacing.s),
                Expanded(
                  child: Text(
                    '${groups.length} eşleşme önerisi bekliyor',
                    style: AppTextStyles.bodyS.copyWith(color: AppColors.info),
                  ),
                ),
                const Icon(
                  Icons.chevron_right,
                  size: AppSizes.iconS,
                  color: AppColors.info,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
