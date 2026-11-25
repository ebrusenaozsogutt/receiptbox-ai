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
import '../../analytics/data/analytics_providers.dart';
import '../../capture/data/capture_providers.dart';
import '../../capture/presentation/review/review_widgets.dart' show CategoryDot;
import '../../home/presentation/home_widgets.dart' show HomeCard;
import '../../transactions/data/transactions_api.dart';
import '../../transactions/data/transactions_providers.dart';
import '../../transactions/domain/spending_category.dart';
import '../data/products_api.dart';
import '../data/products_providers.dart';
import '../domain/product_models.dart';
import 'product_widgets.dart';
import 'refund_dialog.dart';

/// The product card (spec 10.3): name, category, purchase date, merchant, price (and financing
/// cost with installments), documents, warranty (end, days left, source), return window (end,
/// status) and the actions Belgeyi Gör, İade Edildi, Düzenle, Arşivle.
class ProductDetailScreen extends ConsumerWidget {
  const ProductDetailScreen({super.key, required this.productId});

  final String productId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final product = ref.watch(productDetailProvider(productId));
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(title: const Text('Ürün')),
      body: SafeArea(
        child: product.when(
          loading: () => const LoadingView(),
          error: (error, _) => ErrorView(
            message: error is ApiError ? error.message : 'Ürün yüklenemedi.',
            onRetry: () => ref.invalidate(productDetailProvider(productId)),
          ),
          data: (data) => _ProductBody(product: data),
        ),
      ),
    );
  }
}

class _ProductBody extends ConsumerWidget {
  const _ProductBody({required this.product});

  final Product product;

  void _refresh(WidgetRef ref) {
    ref
      ..invalidate(productDetailProvider(product.id))
      ..invalidate(productListProvider)
      ..invalidate(homeDataProvider);
    if (product.transactionId != null) {
      ref
        ..invalidate(purchaseDetailProvider(product.transactionId!))
        ..invalidate(purchaseListProvider);
    }
  }

  Future<void> _run(
    BuildContext context,
    WidgetRef ref,
    Future<Object?> Function() action,
    String done,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await action();
      _refresh(ref);
      messenger.showSnackBar(SnackBar(content: Text(done)));
    } on ApiError catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.message)));
    }
  }

  Future<DateTime?> _pickDate(BuildContext context, DateTime initial) =>
      showDatePicker(
        context: context,
        initialDate: initial,
        firstDate: DateTime(2000),
        lastDate: DateTime(2100),
        locale: const Locale('tr', 'TR'),
      );

  Future<void> _editWarranty(BuildContext context, WidgetRef ref) async {
    final picked = await _pickDate(
      context,
      product.warranty?.endDate ?? DateTime.now(),
    );
    if (picked == null || !context.mounted) return;
    final fromDocument = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Bu tarih nereden?'),
        actions: [
          TextButton(
            key: const Key('warranty_source_user'),
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Kendim girdim'),
          ),
          TextButton(
            key: const Key('warranty_source_document'),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Garanti belgesinde yazıyor'),
          ),
        ],
      ),
    );
    if (fromDocument == null || !context.mounted) return;
    await _run(
      context,
      ref,
      () => ref
          .read(productsApiProvider)
          .putWarranty(
            product.id,
            endDate: picked,
            source: fromDocument
                ? WarrantySource.document
                : WarrantySource.user,
          ),
      'Garanti tarihi kaydedildi.',
    );
  }

  Future<void> _editReturn(BuildContext context, WidgetRef ref) async {
    final picked = await _pickDate(
      context,
      product.returnWindow?.endDate ?? DateTime.now(),
    );
    if (picked == null || !context.mounted) return;
    await _run(
      context,
      ref,
      () => ref
          .read(productsApiProvider)
          .putReturnWindow(
            product.id,
            endDate: picked,
            source: product.channel == PurchaseChannel.online
                ? ReturnSource.user
                : ReturnSource.storePolicy,
          ),
      'İade süresi kaydedildi.',
    );
  }

  Future<void> _returned(BuildContext context, WidgetRef ref) async {
    final api = ref.read(productsApiProvider);
    if (product.transactionId == null) {
      await _run(
        context,
        ref,
        () => api.patch(product.id, {'status': 'RETURNED'}),
        'Ürün iade edildi olarak işaretlendi.',
      );
      return;
    }
    final answer = await showRefundDialog(
      context,
      refundableMinor: product.refundableMinor ?? 0,
      purchaseDate: product.purchaseDate ?? DateTime(2000),
      today: DateTime.now(),
    );
    if (answer == null || !context.mounted) return;
    await _run(
      context,
      ref,
      () => api.refund(
        product.transactionId!,
        amountMinor: answer.amountMinor,
        date: answer.date,
        productId: product.id,
      ),
      'İade kaydedildi.',
    );
  }

  Future<void> _addDocument(BuildContext context, WidgetRef ref) async {
    final picked = await ref.read(galleryPickerProvider).pickImage();
    if (picked == null || !context.mounted) return;
    final name = picked.file.path.toLowerCase();
    await _run(
      context,
      ref,
      () => ref
          .read(documentsApiProvider)
          .upload(
            picked.file,
            mimeType: name.endsWith('.png') ? 'image/png' : 'image/jpeg',
            type: 'WARRANTY',
            productId: product.id,
          ),
      'Garanti belgesi eklendi.',
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final category = product.category ?? SpendingCategory.other;
    final warranty = product.warranty;
    final window = product.returnWindow;
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.screenH),
      children: [
        HomeCard(
          key: const Key('product_header'),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(product.name, style: AppTextStyles.titleL),
                  ),
                  if (!product.isActive)
                    InfoPill(
                      key: const Key('product_status'),
                      label: product.status.label.toUpperCase(),
                      background: AppColors.surfaceAlt,
                      foreground: AppColors.textMuted,
                    ),
                ],
              ),
              const SizedBox(height: AppSpacing.xs),
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
                  ?product.merchant,
                  if (product.purchaseDate != null)
                    formatDateTr(product.purchaseDate!),
                ].join(' · '),
                style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
              ),
              const SizedBox(height: AppSpacing.m),
              Text(
                product.priceMinor == null
                    ? 'Fiyat bilinmiyor'
                    : formatMoneyTl(product.priceMinor!),
                key: const Key('product_price'),
                style: AppTextStyles.display,
              ),
              if (product.financingCostMinor != null)
                Text(
                  'Taksit farkı (finansman maliyeti): '
                  '${formatMoneyTl(product.financingCostMinor!)}',
                  key: const Key('product_financing'),
                  style: AppTextStyles.bodyS.copyWith(color: AppColors.warning),
                ),
              for (final (label, value) in [
                ('Marka', product.brand),
                ('Model', product.model),
                ('Seri no', product.serialNumber),
              ])
                if (value != null)
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.xxs),
                    child: Text('$label: $value', style: AppTextStyles.bodyS),
                  ),
              if (product.transactionId != null)
                TextButton(
                  key: const Key('product_open_purchase'),
                  onPressed: () =>
                      context.push('/transactions/${product.transactionId}'),
                  child: const Text('Harcamayı gör'),
                ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.m),
        HomeCard(
          key: const Key('product_warranty'),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const DeadlineBadge(kind: DeadlineKind.warranty),
                  const Spacer(),
                  if (warranty != null && !warranty.confirmed)
                    const InfoPill(
                      key: Key('warranty_unconfirmed'),
                      label: 'ONAYLANMADI',
                      background: AppColors.warningSoft,
                      foreground: AppColors.warning,
                    ),
                ],
              ),
              const SizedBox(height: AppSpacing.s),
              if (warranty == null)
                Text(
                  'Garanti bilgisi yok.',
                  style: AppTextStyles.body.copyWith(
                    color: AppColors.textMuted,
                  ),
                )
              else ...[
                Text(
                  '${formatDateTr(warranty.endDate)} · '
                  '${daysLeftLabel(warranty.daysLeft)}',
                  key: const Key('warranty_end'),
                  style: AppTextStyles.titleS,
                ),
                Text(
                  warranty.source.label,
                  key: const Key('warranty_source'),
                  style: AppTextStyles.bodyS.copyWith(
                    color: AppColors.textMuted,
                  ),
                ),
              ],
              const SizedBox(height: AppSpacing.s),
              Wrap(
                spacing: AppSpacing.s,
                children: [
                  if (warranty != null && !warranty.confirmed)
                    TextButton(
                      key: const Key('warranty_confirm'),
                      onPressed: () => _run(
                        context,
                        ref,
                        () => ref
                            .read(productsApiProvider)
                            .putWarranty(
                              product.id,
                              endDate: warranty.endDate,
                              source: warranty.source,
                            ),
                        'Garanti onaylandı.',
                      ),
                      child: const Text('Onayla'),
                    ),
                  TextButton(
                    key: const Key('warranty_edit'),
                    onPressed: () => _editWarranty(context, ref),
                    child: Text(
                      warranty == null ? 'Garanti ekle' : 'Tarihi değiştir',
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.m),
        HomeCard(
          key: const Key('product_return'),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const DeadlineBadge(kind: DeadlineKind.returnWindow),
              const SizedBox(height: AppSpacing.s),
              if (window == null)
                Text(
                  product.channel == PurchaseChannel.online
                      ? 'İade süresi girilmedi.'
                      : 'Mağazadan alınan ürünlerde iade süresi mağazaya göre '
                            'değişir; varsayılan yok.',
                  key: const Key('return_none'),
                  style: AppTextStyles.body.copyWith(
                    color: AppColors.textMuted,
                  ),
                )
              else ...[
                Text(
                  window.status == ReturnStatus.open
                      ? '${formatDateTr(window.endDate)} · '
                            '${daysLeftLabel(window.daysLeft)}'
                      : '${formatDateTr(window.endDate)} · ${window.status.label}',
                  key: const Key('return_end'),
                  style: AppTextStyles.titleS,
                ),
                Text(
                  window.source.label,
                  key: const Key('return_source'),
                  style: AppTextStyles.bodyS.copyWith(
                    color: AppColors.textMuted,
                  ),
                ),
              ],
              if (product.isActive)
                TextButton(
                  key: const Key('return_edit'),
                  onPressed: () => _editReturn(context, ref),
                  child: Text(
                    window != null
                        ? 'Tarihi değiştir'
                        : product.channel == PurchaseChannel.online
                        ? 'İade süresini gir'
                        : 'Mağazanın iade süresini gir',
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.m),
        HomeCard(
          key: const Key('product_documents'),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Belgeler', style: AppTextStyles.titleS),
              const SizedBox(height: AppSpacing.xs),
              if (product.documents.isEmpty)
                Text(
                  'Belge yok.',
                  style: AppTextStyles.bodyS.copyWith(
                    color: AppColors.textMuted,
                  ),
                ),
              for (final document in product.documents)
                InkWell(
                  key: Key('product_document_${document.id}'),
                  onTap: () => context.push(
                    '/documents/${document.id}/view?pdf=${document.isPdf}',
                  ),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      vertical: AppSpacing.xs,
                    ),
                    child: Row(
                      children: [
                        Icon(
                          document.isPdf
                              ? Icons.picture_as_pdf_outlined
                              : Icons.image_outlined,
                          size: AppSizes.iconS,
                          color: AppColors.primary,
                        ),
                        const SizedBox(width: AppSpacing.s),
                        Text(
                          _documentLabel(document.type),
                          style: AppTextStyles.body,
                        ),
                      ],
                    ),
                  ),
                ),
              TextButton(
                key: const Key('product_add_document'),
                onPressed: () => _addDocument(context, ref),
                child: const Text('Garanti belgesi ekle'),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.l),
        _ActionGrid(
          actions: [
            OutlinedButton.icon(
              key: const Key('product_view_document'),
              onPressed: product.documents.isEmpty
                  ? null
                  : () {
                      final document = product.documents.first;
                      context.push(
                        '/documents/${document.id}/view?pdf=${document.isPdf}',
                      );
                    },
              icon: const Icon(Icons.description_outlined),
              label: const Text('Belgeyi Gör'),
            ),
            if (product.isActive)
              OutlinedButton.icon(
                key: const Key('product_returned'),
                onPressed: () => _returned(context, ref),
                icon: const Icon(Icons.assignment_return_outlined),
                label: const Text('İade Edildi'),
              ),
            OutlinedButton.icon(
              key: const Key('product_edit'),
              onPressed: () => context.push('/products/${product.id}/edit'),
              icon: const Icon(Icons.edit_outlined),
              label: const Text('Düzenle'),
            ),
            OutlinedButton.icon(
              key: const Key('product_archive'),
              onPressed: () => _run(
                context,
                ref,
                () => ref.read(productsApiProvider).patch(product.id, {
                  'status': product.status == ProductStatus.archived
                      ? 'ACTIVE'
                      : 'ARCHIVED',
                }),
                product.status == ProductStatus.archived
                    ? 'Arşivden çıkarıldı.'
                    : 'Arşivlendi.',
              ),
              icon: const Icon(Icons.archive_outlined),
              label: Text(
                product.status == ProductStatus.archived
                    ? 'Arşivden çıkar'
                    : 'Arşivle',
              ),
            ),
          ],
        ),
      ],
    );
  }
}

/// The four actions of the card, two per row (the theme's buttons are full width).
class _ActionGrid extends StatelessWidget {
  const _ActionGrid({required this.actions});

  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (var i = 0; i < actions.length; i += 2) ...[
          if (i > 0) const SizedBox(height: AppSpacing.s),
          Row(
            children: [
              Expanded(child: actions[i]),
              const SizedBox(width: AppSpacing.s),
              Expanded(
                child: i + 1 < actions.length
                    ? actions[i + 1]
                    : const SizedBox(),
              ),
            ],
          ),
        ],
      ],
    );
  }
}

String _documentLabel(String type) => switch (type) {
  'WARRANTY' => 'Garanti belgesi',
  'INVOICE' => 'Fatura',
  'RECEIPT_IMAGE' => 'Fiş',
  _ => 'Belge',
};
