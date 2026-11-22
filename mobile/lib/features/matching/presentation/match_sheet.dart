import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/utils/date_format.dart';
import '../../../core/utils/money_format.dart';
import '../../../core/widgets/message_banner.dart';
import '../../transactions/data/transactions_api.dart';
import '../../transactions/domain/purchase_models.dart';
import '../domain/match_models.dart';

/// The user's answer to a suggestion: [merged] true = "Birleştir", false = "Ayrı kalsın".
/// [detail] is the purchase that exists now.
class MatchAnswer {
  const MatchAnswer({required this.detail, required this.merged});

  final PurchaseDetail detail;
  final bool merged;
}

/// Asks "Bu işlem daha önce eklediğin Migros fişiyle aynı olabilir. Birleştirilsin mi?" with the
/// two records side by side. [suggestions] are all the candidates of ONE waiting record.
/// Returns null when the sheet is closed without an answer (the question stays open).
Future<MatchAnswer?> showMatchSheet(
  BuildContext context,
  List<MatchSuggestion> suggestions,
) => showModalBottomSheet<MatchAnswer>(
  context: context,
  isScrollControlled: true,
  useRootNavigator: true,
  builder: (_) => MatchSheet(suggestions: suggestions),
);

/// "…fişiyle" / "…banka kaydıyla": how the existing purchase is named in the question.
String _withSuffix(MatchTransaction transaction) {
  final source = transaction.sources.isEmpty ? null : transaction.sources.first;
  final what = switch (source) {
    EvidenceKind.receipt => 'fişiyle',
    EvidenceKind.einvoice => 'e-faturasıyla',
    EvidenceKind.bank => 'banka kaydıyla',
    EvidenceKind.manual => 'kaydıyla',
    null => 'kaydıyla',
  };
  return '${transaction.merchant} $what';
}

class MatchSheet extends ConsumerStatefulWidget {
  const MatchSheet({super.key, required this.suggestions})
    : assert(suggestions.length > 0);

  final List<MatchSuggestion> suggestions;

  @override
  ConsumerState<MatchSheet> createState() => _MatchSheetState();
}

class _MatchSheetState extends ConsumerState<MatchSheet> {
  bool _busy = false;
  String? _problem;

  Future<void> _answer(
    Future<PurchaseDetail> Function(TransactionsApi api) call, {
    required bool merged,
  }) async {
    setState(() {
      _busy = true;
      _problem = null;
    });
    final navigator = Navigator.of(context);
    try {
      final detail = await call(ref.read(transactionsApiProvider));
      if (!mounted) return;
      navigator.pop(MatchAnswer(detail: detail, merged: merged));
    } on ApiError catch (error) {
      if (mounted) {
        setState(() {
          _busy = false;
          _problem = error.message;
        });
      }
    } on Object {
      if (mounted) {
        setState(() {
          _busy = false;
          _problem = 'Cevap kaydedilemedi. Tekrar dene.';
        });
      }
    }
  }

  void _accept(MatchSuggestion suggestion) =>
      unawaited(_answer((api) => api.acceptMatch(suggestion.id), merged: true));

  void _reject() => unawaited(
    _answer(
      (api) => api.rejectMatch(widget.suggestions.first.id),
      merged: false,
    ),
  );

  @override
  Widget build(BuildContext context) {
    final suggestions = widget.suggestions;
    final observation = suggestions.first.observation;
    final single = suggestions.length == 1;
    return SafeArea(
      child: SingleChildScrollView(
        key: const Key('match_sheet'),
        padding: const EdgeInsets.all(AppSpacing.screenH),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Aynı harcama olabilir mi?', style: AppTextStyles.titleM),
            const SizedBox(height: AppSpacing.s),
            Text(
              single
                  ? 'Bu işlem daha önce eklediğin '
                        '${_withSuffix(suggestions.first.transaction)} aynı '
                        'olabilir. Birleştirilsin mi?'
                  : 'Bu işlem daha önce eklediğin birkaç harcamayla aynı '
                        'olabilir. Hangisiyle birleştirilsin?',
              key: const Key('match_question'),
              style: AppTextStyles.body.copyWith(color: AppColors.textMuted),
            ),
            const SizedBox(height: AppSpacing.l),
            if (single)
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: _SideCard(
                      key: const Key('match_new'),
                      title: 'YENİ KAYIT',
                      merchant: observation.merchant,
                      date: observation.date,
                      time: observation.time,
                      totalMinor: observation.totalMinor,
                      sources: [observation.source],
                    ),
                  ),
                  const SizedBox(width: AppSpacing.s),
                  Expanded(
                    child: _SideCard(
                      key: const Key('match_existing'),
                      title: 'MEVCUT HARCAMA',
                      merchant: suggestions.first.transaction.merchant,
                      date: suggestions.first.transaction.date,
                      time: suggestions.first.transaction.time,
                      totalMinor: suggestions.first.transaction.totalMinor,
                      sources: suggestions.first.transaction.sources,
                    ),
                  ),
                ],
              )
            else ...[
              _SideCard(
                key: const Key('match_new'),
                title: 'YENİ KAYIT',
                merchant: observation.merchant,
                date: observation.date,
                time: observation.time,
                totalMinor: observation.totalMinor,
                sources: [observation.source],
              ),
              for (final suggestion in suggestions) ...[
                const SizedBox(height: AppSpacing.s),
                _SideCard(
                  key: Key('match_candidate_${suggestion.id}'),
                  title: 'MEVCUT HARCAMA',
                  merchant: suggestion.transaction.merchant,
                  date: suggestion.transaction.date,
                  time: suggestion.transaction.time,
                  totalMinor: suggestion.transaction.totalMinor,
                  sources: suggestion.transaction.sources,
                  action: OutlinedButton(
                    key: Key('match_accept_${suggestion.id}'),
                    onPressed: _busy ? null : () => _accept(suggestion),
                    child: const Text('Bununla birleştir'),
                  ),
                ),
              ],
            ],
            if (_problem != null) ...[
              const SizedBox(height: AppSpacing.m),
              MessageBanner(_problem!),
            ],
            const SizedBox(height: AppSpacing.l),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    key: const Key('match_reject'),
                    onPressed: _busy ? null : _reject,
                    child: const Text('Ayrı kalsın'),
                  ),
                ),
                if (single) ...[
                  const SizedBox(width: AppSpacing.m),
                  Expanded(
                    child: FilledButton(
                      key: Key('match_accept_${suggestions.first.id}'),
                      onPressed: _busy
                          ? null
                          : () => _accept(suggestions.first),
                      child: _busy
                          ? const SizedBox(
                              width: AppSizes.iconS,
                              height: AppSizes.iconS,
                              child: CircularProgressIndicator(
                                strokeWidth: AppSizes.progressThickness - 1,
                              ),
                            )
                          : const Text('Birleştir'),
                    ),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// One of the two records of the question: where it came from, what it says.
class _SideCard extends StatelessWidget {
  const _SideCard({
    super.key,
    required this.title,
    required this.merchant,
    required this.date,
    required this.time,
    required this.totalMinor,
    required this.sources,
    this.action,
  });

  final String title;
  final String merchant;
  final DateTime date;
  final TimeOfDay? time;
  final int totalMinor;
  final List<EvidenceKind> sources;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.m),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.card,
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: AppTextStyles.overline.copyWith(color: AppColors.textMuted),
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(merchant, style: AppTextStyles.bodyStrong),
          const SizedBox(height: AppSpacing.xxs),
          Text(formatMoneyTl(totalMinor), style: AppTextStyles.titleS),
          const SizedBox(height: AppSpacing.xxs),
          Text(
            [
              formatDateTr(date),
              if (time != null) timeLabel(time!),
            ].join(' · '),
            style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
          ),
          const SizedBox(height: AppSpacing.xs),
          Wrap(
            spacing: AppSpacing.xs,
            runSpacing: AppSpacing.xs,
            children: [
              for (final source in sources)
                Text(
                  source.label,
                  style: AppTextStyles.caption.copyWith(
                    color: AppColors.primary,
                  ),
                ),
            ],
          ),
          if (action != null) ...[
            const SizedBox(height: AppSpacing.s),
            SizedBox(width: double.infinity, child: action),
          ],
        ],
      ),
    );
  }
}
