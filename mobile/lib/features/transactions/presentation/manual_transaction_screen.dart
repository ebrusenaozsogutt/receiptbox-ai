import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../../core/widgets/message_banner.dart';
import '../../capture/domain/review_form.dart';
import '../../capture/presentation/review/fields_card.dart';
import '../../installments/data/installment_providers.dart';
import '../../matching/data/matching_providers.dart';
import '../../matching/domain/match_models.dart';
import '../../matching/presentation/match_sheet.dart';
import '../../matching/presentation/merge_feedback.dart';
import '../data/transactions_api.dart';
import '../data/transactions_providers.dart';
import '../domain/purchase_models.dart';

/// "Manuel Harcama": a purchase typed in by hand. With [purchaseId] it edits a saved purchase.
class ManualTransactionScreen extends ConsumerWidget {
  const ManualTransactionScreen({super.key, this.purchaseId});

  final String? purchaseId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final id = purchaseId;
    if (id == null) {
      return _FormScaffold(
        title: 'Manuel Harcama',
        initial: ReviewForm.blank(DateTime.now()),
      );
    }
    final detail = ref.watch(purchaseDetailProvider(id));
    return detail.when(
      loading: () => Scaffold(
        appBar: AppBar(title: const Text('Harcamayı düzenle')),
        body: const LoadingView(),
      ),
      error: (error, _) => Scaffold(
        appBar: AppBar(title: const Text('Harcamayı düzenle')),
        body: ErrorView(
          message: error is ApiError ? error.message : 'Harcama yüklenemedi.',
          onRetry: () => ref.invalidate(purchaseDetailProvider(id)),
        ),
      ),
      data: (data) => _FormScaffold(
        title: 'Harcamayı düzenle',
        initial: ReviewForm.fromPurchase(data.purchase),
        purchaseId: id,
      ),
    );
  }
}

class _FormScaffold extends ConsumerStatefulWidget {
  const _FormScaffold({
    required this.title,
    required this.initial,
    this.purchaseId,
  });

  final String title;
  final ReviewForm initial;
  final String? purchaseId;

  @override
  ConsumerState<_FormScaffold> createState() => _FormScaffoldState();
}

class _FormScaffoldState extends ConsumerState<_FormScaffold> {
  late ReviewForm _form = widget.initial;
  bool _saving = false;
  String? _problem;

  void _change(ReviewForm Function(ReviewForm form) edit) =>
      setState(() => _form = edit(_form));

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _problem = null;
    });
    final messenger = ScaffoldMessenger.of(context);
    final router = GoRouter.of(context);
    try {
      final input = PurchaseInput(
        merchant: _form.merchant,
        date: _form.date,
        time: _form.time,
        totalMinor: _form.totalMinor!,
        category: _form.category,
        channel: _form.channel,
        note: _form.note,
        installmentCount: _form.installmentCount,
      );
      final api = ref.read(transactionsApiProvider);
      final container = ProviderScope.containerOf(context);
      final id = widget.purchaseId;
      SaveResult? saved;
      if (id == null) {
        saved = await api.createManual(input);
      } else {
        await api.update(id, input);
        ref.invalidate(purchaseDetailProvider(id));
      }
      ref
        ..invalidate(purchaseListProvider)
        ..invalidate(installmentScheduleProvider)
        ..invalidate(pendingMatchesProvider);
      var message = id == null
          ? 'Harcama kaydedildi.'
          : 'Değişiklikler kaydedildi.';
      if (saved is NeedsAnswer) {
        // It may be a purchase you already have (P09): ask before anything is created.
        if (!mounted) return;
        final answer = await showMatchSheet(context, saved.suggestions);
        ref
          ..invalidate(purchaseListProvider)
          ..invalidate(installmentScheduleProvider)
          ..invalidate(pendingMatchesProvider);
        message = answer == null
            ? 'Eşleşme sorusu bekliyor. Harcamalar ekranından cevaplayabilirsin.'
            : answer.merged
            ? 'Mevcut harcamayla birleştirildi.'
            : 'Harcama kaydedildi.';
      }
      final merge = saved is Saved ? saved.detail.merge : null;
      if (saved is Saved && merge != null && merge.isAuto) {
        showMergedSnackBar(
          messenger: messenger,
          container: container,
          message: 'Bu harcama mevcut bir kayıtla eşleşti ve birleştirildi.',
          merges: [
            UndoableMerge(
              transactionId: saved.detail.purchase.id,
              observationId: merge.observationId,
            ),
          ],
        );
      } else {
        messenger.showSnackBar(SnackBar(content: Text(message)));
      }
      if (id == null) {
        router.go('/transactions');
      } else {
        router.pop();
      }
    } on ApiError catch (error) {
      if (mounted) {
        setState(() {
          _saving = false;
          _problem = error.message;
        });
      }
    } on Object {
      if (mounted) {
        setState(() {
          _saving = false;
          _problem = 'Kaydedilemedi. Tekrar dene.';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(title: Text(widget.title)),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(AppSpacing.screenH),
                children: [
                  if (_problem != null) ...[
                    MessageBanner(_problem!),
                    const SizedBox(height: AppSpacing.m),
                  ],
                  FieldsCard(
                    form: _form,
                    onMerchant: (v) => _change((f) => f.copyWith(merchant: v)),
                    onDate: (v) => _change(
                      (f) => f.copyWith(date: DateTime(v.year, v.month, v.day)),
                    ),
                    onTime: (v) => _change((f) => f.copyWith(time: () => v)),
                    onTotal: (v) =>
                        _change((f) => f.copyWith(totalMinor: () => v)),
                    onCategory: (v) => _change((f) => f.copyWith(category: v)),
                    onChannel: (v) => _change((f) => f.copyWith(channel: v)),
                    onNote: (v) => _change((f) => f.copyWith(note: v)),
                    onInstallments: widget.purchaseId == null
                        ? (v) => _change(
                            (f) => f.copyWith(installmentCount: () => v),
                          )
                        : null,
                  ),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.screenH,
                vertical: AppSpacing.m,
              ),
              decoration: const BoxDecoration(
                color: AppColors.surface,
                border: Border(top: BorderSide(color: AppColors.border)),
              ),
              child: SizedBox(
                width: double.infinity,
                child: FilledButton(
                  key: const Key('manual_save'),
                  onPressed: _saving || !_form.canSave ? null : _save,
                  child: _saving
                      ? const SizedBox(
                          width: AppSizes.iconS,
                          height: AppSizes.iconS,
                          child: CircularProgressIndicator(
                            strokeWidth: AppSizes.progressThickness - 1,
                          ),
                        )
                      : const Text('Kaydet'),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
