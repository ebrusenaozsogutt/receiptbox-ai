import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/utils/date_format.dart';
import '../../../core/utils/money_format.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../capture/presentation/review/review_widgets.dart';
import '../../installments/data/installment_providers.dart';
import '../../installments/domain/installment_models.dart';
import '../../installments/presentation/installment_widgets.dart';
import '../../matching/data/matching_providers.dart';
import '../data/document_providers.dart';
import '../data/transactions_api.dart';
import '../data/transactions_providers.dart';
import '../domain/purchase_models.dart';
import '../domain/spending_category.dart';

/// One purchase: amount, where it came from (evidence), lines, and its stored receipt image.
class TransactionDetailScreen extends ConsumerWidget {
  const TransactionDetailScreen({super.key, required this.purchaseId});

  final String purchaseId;

  Future<void> _delete(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Harcama silinsin mi?'),
        content: const Text(
          'Bu harcama ve fiş görseli silinecek. Bu işlem geri alınamaz.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Vazgeç'),
          ),
          TextButton(
            key: const Key('delete_confirm'),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Sil'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    final router = GoRouter.of(context);
    try {
      await ref.read(transactionsApiProvider).delete(purchaseId);
      ref.invalidate(purchaseListProvider);
      messenger.showSnackBar(const SnackBar(content: Text('Harcama silindi.')));
      router.go('/transactions');
    } on ApiError catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.message)));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(purchaseDetailProvider(purchaseId));
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        title: const Text('Harcama'),
        actions: [
          if (detail.hasValue) ...[
            IconButton(
              key: const Key('edit_button'),
              tooltip: 'Düzenle',
              icon: const Icon(Icons.edit_outlined),
              onPressed: () => context.push('/transactions/$purchaseId/edit'),
            ),
            IconButton(
              key: const Key('delete_button'),
              tooltip: 'Sil',
              icon: const Icon(Icons.delete_outline),
              onPressed: () => _delete(context, ref),
            ),
          ],
        ],
      ),
      body: SafeArea(
        child: detail.when(
          loading: () => const LoadingView(),
          error: (error, _) => ErrorView(
            message: error is ApiError ? error.message : 'Harcama yüklenemedi.',
            onRetry: () => ref.invalidate(purchaseDetailProvider(purchaseId)),
          ),
          data: (data) => _DetailBody(detail: data, purchaseId: purchaseId),
        ),
      ),
    );
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.l),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.card,
        border: Border.all(color: AppColors.border),
      ),
      child: child,
    );
  }
}

class _DetailBody extends ConsumerWidget {
  const _DetailBody({required this.detail, required this.purchaseId});

  final PurchaseDetail detail;
  final String purchaseId;

  /// "Ayır" (P09): one record of a merged purchase becomes a purchase of its own.
  Future<void> _separate(
    BuildContext context,
    WidgetRef ref,
    EvidenceItem item,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('${item.kind.label} kaydı ayrılsın mı?'),
        content: const Text(
          'Bu kayıt ayrı bir harcama olur. Aynı alışveriş iki harcama olarak '
          'sayılır.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Vazgeç'),
          ),
          TextButton(
            key: const Key('separate_confirm'),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Ayır'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref
          .read(transactionsApiProvider)
          .unmerge(purchaseId, item.observationId);
      ref
        ..invalidate(purchaseDetailProvider(purchaseId))
        ..invalidate(purchaseListProvider)
        ..invalidate(pendingMatchesProvider);
      messenger.showSnackBar(
        const SnackBar(
          content: Text('Kayıtlar ayrıldı: iki ayrı harcama var.'),
        ),
      );
    } on ApiError catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.message)));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final purchase = detail.purchase;
    final category = purchase.category ?? SpendingCategory.other;
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.screenH),
      children: [
        _Card(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(purchase.merchant, style: AppTextStyles.titleL),
              const SizedBox(height: AppSpacing.xxs),
              Text(
                formatMoneyTl(purchase.totalMinor),
                key: const Key('detail_total'),
                style: AppTextStyles.display,
              ),
              const SizedBox(height: AppSpacing.m),
              Row(
                children: [
                  CategoryDot(color: category.color),
                  const SizedBox(width: AppSpacing.s),
                  Text(category.label, style: AppTextStyles.body),
                ],
              ),
              const SizedBox(height: AppSpacing.xs),
              Text(
                [
                  formatDateTr(purchase.date),
                  if (purchase.time != null) timeLabel(purchase.time!),
                  if (purchase.channel != PurchaseChannel.unknown)
                    purchase.channel.label,
                ].join(' · '),
                style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
              ),
              if (purchase.note != null) ...[
                const SizedBox(height: AppSpacing.m),
                Text(purchase.note!, style: AppTextStyles.body),
              ],
              const SizedBox(height: AppSpacing.m),
              Wrap(
                spacing: AppSpacing.s,
                runSpacing: AppSpacing.s,
                children: [
                  // one chip per kind: a purchase paid in installments has several bank rows
                  for (final kind in detail.evidence.toSet())
                    Chip(
                      key: Key('evidence_${kind.name}'),
                      label: Text(
                        detail.evidence.where((k) => k == kind).length > 1
                            ? '${kind.label} (${detail.evidence.where((k) => k == kind).length})'
                            : kind.label,
                      ),
                      avatar: const Icon(Icons.check, size: AppSizes.iconS),
                    ),
                ],
              ),
              if (detail.isMerged) ...[
                const SizedBox(height: AppSpacing.m),
                Text('Birleşmiş kayıtlar', style: AppTextStyles.titleS),
                for (final item in detail.mergedRecords)
                  Container(
                    padding: const EdgeInsets.symmetric(
                      vertical: AppSpacing.xs,
                    ),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            item.amountMinor == null
                                ? item.kind.label
                                : '${item.kind.label} · '
                                      '${formatMoneyTl(item.amountMinor!)}',
                            style: AppTextStyles.body,
                          ),
                        ),
                        TextButton(
                          key: Key('separate_${item.observationId}'),
                          onPressed: () => _separate(context, ref, item),
                          child: const Text('Ayır'),
                        ),
                      ],
                    ),
                  ),
              ],
            ],
          ),
        ),
        if (detail.plan != null || !purchase.isEstimated) ...[
          const SizedBox(height: AppSpacing.m),
          _PlanCard(detail: detail, purchaseId: purchaseId),
        ],
        if (detail.documents.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.m),
          _Card(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Belgeler', style: AppTextStyles.titleS),
                const SizedBox(height: AppSpacing.m),
                Wrap(
                  spacing: AppSpacing.m,
                  runSpacing: AppSpacing.m,
                  children: [
                    for (final document in detail.documents)
                      _DocumentThumb(document: document),
                  ],
                ),
              ],
            ),
          ),
        ],
        if (detail.lines.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.m),
          _Card(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Kalemler (${detail.lines.length})',
                  style: AppTextStyles.titleS,
                ),
                const SizedBox(height: AppSpacing.s),
                for (final line in detail.lines)
                  Container(
                    padding: const EdgeInsets.symmetric(
                      vertical: AppSpacing.rowV,
                    ),
                    decoration: const BoxDecoration(
                      border: Border(top: BorderSide(color: AppColors.border)),
                    ),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(line.name, style: AppTextStyles.body),
                        ),
                        if (line.totalMinor != null)
                          Text(
                            formatMoneyTl(line.totalMinor!),
                            style: AppTextStyles.bodyStrong,
                          ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

/// "Taksit" (P10): the plan of a purchase and its payments. Payments are not spending.
class _PlanCard extends ConsumerWidget {
  const _PlanCard({required this.detail, required this.purchaseId});

  final PurchaseDetail detail;
  final String purchaseId;

  Future<int?> _askCount(BuildContext context, int initial) {
    return showDialog<int>(
      context: context,
      builder: (dialogContext) {
        var count = initial;
        return StatefulBuilder(
          builder: (context, setState) => AlertDialog(
            title: const Text('Kaç taksit?'),
            content: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                IconButton(
                  key: const Key('plan_minus'),
                  icon: const Icon(Icons.remove_circle_outline),
                  onPressed: count > 2 ? () => setState(() => count--) : null,
                ),
                Text(
                  '$count',
                  key: const Key('plan_count'),
                  style: AppTextStyles.titleL,
                ),
                IconButton(
                  key: const Key('plan_plus'),
                  icon: const Icon(Icons.add_circle_outline),
                  onPressed: count < 36 ? () => setState(() => count++) : null,
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(),
                child: const Text('Vazgeç'),
              ),
              TextButton(
                key: const Key('plan_confirm'),
                onPressed: () => Navigator.of(dialogContext).pop(count),
                child: const Text('Kaydet'),
              ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _run(
    BuildContext context,
    WidgetRef ref,
    Future<PurchaseDetail> Function() action,
    String done,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await action();
      ref
        ..invalidate(purchaseDetailProvider(purchaseId))
        ..invalidate(purchaseListProvider)
        ..invalidate(installmentScheduleProvider);
      messenger.showSnackBar(SnackBar(content: Text(done)));
    } on ApiError catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.message)));
    }
  }

  Future<void> _setCount(
    BuildContext context,
    WidgetRef ref,
    int initial,
  ) async {
    final count = await _askCount(context, initial);
    if (count == null || !context.mounted) return;
    await _run(
      context,
      ref,
      () => ref.read(transactionsApiProvider).putPlan(purchaseId, count: count),
      'Taksit planı kaydedildi: $count taksit.',
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final plan = detail.plan;
    final api = ref.read(transactionsApiProvider);
    if (plan == null) {
      return _Card(
        child: Row(
          children: [
            Expanded(child: Text('Taksit', style: AppTextStyles.titleS)),
            TextButton(
              key: const Key('plan_add'),
              onPressed: () => _setCount(context, ref, 3),
              child: const Text('Taksitli yap'),
            ),
          ],
        ),
      );
    }
    return _Card(
      child: Column(
        key: const Key('plan_card'),
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('Taksit', style: AppTextStyles.titleS),
              const SizedBox(width: AppSpacing.s),
              InstallmentBadge(label: '${plan.count} TAKSİT'),
              if (detail.purchase.isEstimated) ...[
                const SizedBox(width: AppSpacing.s),
                const EstimatedBadge(),
              ],
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            plan.isActive
                ? '${plan.observedCount}/${plan.count} taksit bankada görüldü. '
                      'Harcama alışveriş ayında bir kez sayılır; taksitler ödemedir.'
                : plan.status == PlanStatus.completed
                ? 'Tüm taksitler görüldü.'
                : 'Plan iptal edildi.',
            key: const Key('plan_summary'),
            style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
          ),
          if (detail.purchase.isEstimated) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Bu alışveriş bir banka taksit satırından tahmin edildi. Fişini '
              'eklersen tutar ve tarih düzelir.',
              key: const Key('plan_estimated_note'),
              style: AppTextStyles.bodyS.copyWith(color: AppColors.warning),
            ),
          ],
          const SizedBox(height: AppSpacing.m),
          for (final payment in plan.payments)
            Container(
              key: Key('plan_payment_${payment.seq}'),
              padding: const EdgeInsets.symmetric(vertical: AppSpacing.rowV),
              decoration: const BoxDecoration(
                border: Border(top: BorderSide(color: AppColors.border)),
              ),
              child: Row(
                children: [
                  PaymentDot(status: payment.status),
                  const SizedBox(width: AppSpacing.m),
                  Expanded(
                    child: Text(
                      '${payment.seq}. taksit · '
                      '${formatMonthTr(payment.dueMonth)}',
                      style: AppTextStyles.body,
                    ),
                  ),
                  Text(
                    formatMoneyTl(payment.amountMinor),
                    style: AppTextStyles.bodyStrong,
                  ),
                ],
              ),
            ),
          const SizedBox(height: AppSpacing.s),
          Wrap(
            spacing: AppSpacing.l,
            runSpacing: AppSpacing.xs,
            children: [
              for (final status in PaymentStatus.values)
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    PaymentDot(status: status),
                    const SizedBox(width: AppSpacing.xs),
                    Text(
                      status.label,
                      style: AppTextStyles.caption.copyWith(
                        color: AppColors.textMuted,
                      ),
                    ),
                  ],
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.s),
          Wrap(
            spacing: AppSpacing.s,
            children: [
              if (plan.isActive && plan.observedCount == 0)
                TextButton(
                  key: const Key('plan_change'),
                  onPressed: () => _setCount(context, ref, plan.count),
                  child: const Text('Taksit sayısını değiştir'),
                ),
              if (plan.status == PlanStatus.cancelled)
                TextButton(
                  key: const Key('plan_reopen'),
                  onPressed: () => _run(
                    context,
                    ref,
                    () => api.setPlanCancelled(plan.id, cancel: false),
                    'Plan yeniden açıldı.',
                  ),
                  child: const Text('Planı yeniden aç'),
                )
              else
                TextButton(
                  key: const Key('plan_cancel'),
                  onPressed: () => _run(
                    context,
                    ref,
                    () => api.setPlanCancelled(plan.id, cancel: true),
                    'Plan iptal edildi.',
                  ),
                  child: const Text('Planı iptal et'),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

/// A small preview of a stored document (loaded with a short-lived token); tap to enlarge.
class _DocumentThumb extends ConsumerWidget {
  const _DocumentThumb({required this.document});

  final DocumentInfo document;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final preview = ref.watch(documentPreviewProvider(document));
    return InkWell(
      key: Key('document_${document.id}'),
      borderRadius: AppRadius.circular(AppRadius.thumbnail),
      onTap: () =>
          context.push('/documents/${document.id}/view?pdf=${document.isPdf}'),
      child: ClipRRect(
        borderRadius: AppRadius.circular(AppRadius.thumbnail),
        child: Container(
          width: AppSizes.documentThumb,
          height: AppSizes.documentThumb,
          color: AppColors.surfaceAlt,
          child: preview.when(
            data: (bytes) => Image.memory(
              bytes,
              fit: BoxFit.cover,
              alignment: Alignment.topCenter,
              errorBuilder: (_, _, _) =>
                  const _ThumbIcon(Icons.broken_image_outlined),
            ),
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (_, _) => _ThumbIcon(
              document.isPdf
                  ? Icons.picture_as_pdf_outlined
                  : Icons.broken_image_outlined,
            ),
          ),
        ),
      ),
    );
  }
}

class _ThumbIcon extends StatelessWidget {
  const _ThumbIcon(this.icon);

  final IconData icon;

  @override
  Widget build(BuildContext context) =>
      Icon(icon, color: AppColors.textSubtle, size: AppSizes.icon);
}

/// Full-screen view of one document (zoom with two fingers). A PDF shows its first page.
class DocumentViewerScreen extends ConsumerWidget {
  const DocumentViewerScreen({
    super.key,
    required this.documentId,
    required this.isPdf,
  });

  final String documentId;
  final bool isPdf;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final preview = ref.watch(
      documentPreviewProvider(
        DocumentInfo(
          id: documentId,
          type: '',
          mimeType: isPdf ? 'application/pdf' : 'image/jpeg',
        ),
      ),
    );
    return Scaffold(
      backgroundColor: AppColors.cameraBackground,
      appBar: AppBar(
        backgroundColor: AppColors.cameraBackground,
        foregroundColor: AppColors.cameraForeground,
        iconTheme: const IconThemeData(color: AppColors.cameraForeground),
        title: Text(
          'Belge',
          style: AppTextStyles.titleM.copyWith(
            color: AppColors.cameraForeground,
          ),
        ),
      ),
      body: SafeArea(
        child: preview.when(
          loading: () => const LoadingView(),
          error: (error, _) => ErrorView(
            message: error is ApiError ? error.message : 'Belge açılamadı.',
          ),
          data: (bytes) => InteractiveViewer(
            maxScale: 5,
            child: Center(child: Image.memory(bytes)),
          ),
        ),
      ),
    );
  }
}
