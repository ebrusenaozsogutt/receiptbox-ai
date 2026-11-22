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
        content: const Text('Bu harcama ve fiş görseli silinecek. Bu işlem geri alınamaz.'),
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
        const SnackBar(content: Text('Kayıtlar ayrıldı: iki ayrı harcama var.')),
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
                  for (final kind in detail.evidence)
                    Chip(
                      key: Key('evidence_${kind.name}'),
                      label: Text(kind.label),
                      avatar: const Icon(Icons.check, size: AppSizes.iconS),
                    ),
                ],
              ),
              if (detail.isMerged) ...[
                const SizedBox(height: AppSpacing.m),
                Text('Birleşmiş kayıtlar', style: AppTextStyles.titleS),
                for (final item in detail.evidenceItems)
                  Container(
                    padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
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
                Text('Kalemler (${detail.lines.length})', style: AppTextStyles.titleS),
                const SizedBox(height: AppSpacing.s),
                for (final line in detail.lines)
                  Container(
                    padding: const EdgeInsets.symmetric(vertical: AppSpacing.rowV),
                    decoration: const BoxDecoration(
                      border: Border(top: BorderSide(color: AppColors.border)),
                    ),
                    child: Row(
                      children: [
                        Expanded(child: Text(line.name, style: AppTextStyles.body)),
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
      onTap: () => context.push('/documents/${document.id}/view?pdf=${document.isPdf}'),
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
              errorBuilder: (_, _, _) => const _ThumbIcon(Icons.broken_image_outlined),
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
          style: AppTextStyles.titleM.copyWith(color: AppColors.cameraForeground),
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
