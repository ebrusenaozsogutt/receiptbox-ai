import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/utils/date_format.dart';
import '../../../core/utils/money_format.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../../core/widgets/screen_header.dart';
import '../../capture/presentation/review/review_widgets.dart' show CategoryDot;
import '../../home/presentation/home_widgets.dart' show HomeCard;
import '../../transactions/domain/spending_category.dart';
import '../data/products_api.dart';
import '../data/products_providers.dart';
import '../domain/product_models.dart';
import 'product_widgets.dart';

/// "Ürünler": suggestions, "Teknoloji Kasam" (technology products by warranty days left) and the
/// other products, with filter chips. No Figma frame: tokens and the home cards.
class ProductsScreen extends ConsumerWidget {
  const ProductsScreen({super.key});

  Future<void> _track(
    BuildContext context,
    WidgetRef ref,
    ProductSuggestion suggestion,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    final router = GoRouter.of(context);
    try {
      final product = await ref
          .read(productsApiProvider)
          .create(
            ProductInput(
              transactionId: suggestion.transactionId,
              receiptItemId: suggestion.receiptItemId,
            ),
          );
      ref
        ..invalidate(productListProvider)
        ..invalidate(productSuggestionsProvider);
      router.push('/products/${product.id}');
    } on ApiError catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.message)));
    }
  }

  Future<void> _dismiss(WidgetRef ref, ProductSuggestion suggestion) async {
    await ref.read(productsApiProvider).dismiss(suggestion);
    ref.invalidate(productSuggestionsProvider);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final products = ref.watch(productListProvider);
    final suggestions = ref.watch(productSuggestionsProvider).value ?? const [];
    final filter = ref.watch(productFilterControllerProvider);
    return SafeArea(
      child: Column(
        children: [
          ScreenHeader(
            title: 'Ürünler',
            actions: [
              IconButton(
                key: const Key('add_product_button'),
                tooltip: 'Ürün ekle',
                icon: const Icon(Icons.add, color: AppColors.primary),
                onPressed: () => context.push('/products/new'),
              ),
            ],
          ),
          SizedBox(
            height: AppSizes.minTapTarget,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.screenH,
              ),
              children: [
                for (final f in ProductFilter.values) ...[
                  ChoiceChip(
                    key: Key('product_filter_${f.name}'),
                    label: Text(f.label),
                    selected: f == filter,
                    onSelected: (_) => ref
                        .read(productFilterControllerProvider.notifier)
                        .set(f),
                  ),
                  const SizedBox(width: AppSpacing.s),
                ],
              ],
            ),
          ),
          Expanded(
            child: products.when(
              loading: () => const LoadingView(),
              error: (error, _) => ErrorView(
                message: error is ApiError
                    ? error.message
                    : 'Ürünler yüklenemedi.',
                onRetry: () => ref.invalidate(productListProvider),
              ),
              data: (items) => RefreshIndicator(
                onRefresh: () async {
                  ref
                    ..invalidate(productListProvider)
                    ..invalidate(productSuggestionsProvider);
                },
                child: _ProductsBody(
                  products: items.where(filter.matches).toList(),
                  suggestions:
                      filter == ProductFilter.all ||
                          filter == ProductFilter.active
                      ? suggestions
                      : const [],
                  onTrack: (s) => _track(context, ref, s),
                  onDismiss: (s) => _dismiss(ref, s),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProductsBody extends StatelessWidget {
  const _ProductsBody({
    required this.products,
    required this.suggestions,
    required this.onTrack,
    required this.onDismiss,
  });

  final List<Product> products;
  final List<ProductSuggestion> suggestions;
  final ValueChanged<ProductSuggestion> onTrack;
  final ValueChanged<ProductSuggestion> onDismiss;

  @override
  Widget build(BuildContext context) {
    // "Teknoloji Kasam": the technology products, the warranty that ends first on top.
    final vault =
        products
            .where(
              (p) => p.category == SpendingCategory.technology && p.isActive,
            )
            .toList()
          ..sort(
            (a, b) => (a.warranty?.daysLeft ?? 1 << 30).compareTo(
              b.warranty?.daysLeft ?? 1 << 30,
            ),
          );
    final others = products.where((p) => !vault.contains(p)).toList();
    if (products.isEmpty && suggestions.isEmpty) {
      return ListView(
        children: const [
          EmptyState(
            icon: Icons.inventory_2_outlined,
            title: 'Ürünlerin burada olacak',
            message: 'Garantisini ve iade süresini takip etmek istediğin ürünleri ekle.',
          ),
        ],
      );
    }
    return ListView(
      key: const Key('products_list'),
      padding: const EdgeInsets.all(AppSpacing.screenH),
      children: [
        if (suggestions.isNotEmpty) ...[
          Text('Öneriler', style: AppTextStyles.titleM),
          const SizedBox(height: AppSpacing.s),
          for (final s in suggestions) ...[
            _SuggestionCard(
              suggestion: s,
              onTrack: () => onTrack(s),
              onDismiss: () => onDismiss(s),
            ),
            const SizedBox(height: AppSpacing.s),
          ],
          const SizedBox(height: AppSpacing.m),
        ],
        if (vault.isNotEmpty) ...[
          Text('Teknoloji Kasam', style: AppTextStyles.titleM),
          const SizedBox(height: AppSpacing.xxs),
          Text(
            'Garantisi önce bitecek olan en üstte.',
            style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
          ),
          const SizedBox(height: AppSpacing.s),
          HomeCard(
            key: const Key('technology_vault'),
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.l),
            child: Column(
              children: [
                for (var i = 0; i < vault.length; i++)
                  _ProductTile(product: vault[i], first: i == 0),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.l),
        ],
        if (others.isNotEmpty) ...[
          Text(
            vault.isEmpty ? 'Ürünler' : 'Diğer ürünler',
            style: AppTextStyles.titleM,
          ),
          const SizedBox(height: AppSpacing.s),
          HomeCard(
            key: const Key('other_products'),
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.l),
            child: Column(
              children: [
                for (var i = 0; i < others.length; i++)
                  _ProductTile(product: others[i], first: i == 0),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

class _SuggestionCard extends StatelessWidget {
  const _SuggestionCard({
    required this.suggestion,
    required this.onTrack,
    required this.onDismiss,
  });

  final ProductSuggestion suggestion;
  final VoidCallback onTrack;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    return HomeCard(
      key: Key('suggestion_${suggestion.transactionId}'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(suggestion.name, style: AppTextStyles.bodyStrong),
          Text(
            '${suggestion.merchant} · ${formatDateTr(suggestion.purchaseDate)} · '
            '${formatMoneyTl(suggestion.priceMinor)}',
            style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
          ),
          const SizedBox(height: AppSpacing.s),
          Row(
            children: [
              Expanded(
                child: FilledButton(
                  key: Key('suggestion_track_${suggestion.transactionId}'),
                  onPressed: onTrack,
                  child: const Text('Takip et'),
                ),
              ),
              const SizedBox(width: AppSpacing.s),
              Expanded(
                child: TextButton(
                  key: Key('suggestion_dismiss_${suggestion.transactionId}'),
                  onPressed: onDismiss,
                  child: const Text('Bir daha sorma'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ProductTile extends StatelessWidget {
  const _ProductTile({required this.product, required this.first});

  final Product product;
  final bool first;

  @override
  Widget build(BuildContext context) {
    final warranty = product.warranty;
    final subtitle = [
      ?product.merchant,
      if (product.purchaseDate != null) formatDateTr(product.purchaseDate!),
    ].join(' · ');
    return InkWell(
      key: Key('product_${product.id}'),
      onTap: () => context.push('/products/${product.id}'),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.rowV),
        decoration: BoxDecoration(
          border: first
              ? null
              : const Border(top: BorderSide(color: AppColors.border)),
        ),
        child: Row(
          children: [
            CategoryDot(
              color: (product.category ?? SpendingCategory.other).color,
            ),
            const SizedBox(width: AppSpacing.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    product.name,
                    style: AppTextStyles.bodyStrong,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (subtitle.isNotEmpty)
                    Text(
                      subtitle,
                      style: AppTextStyles.bodyS.copyWith(
                        color: AppColors.textMuted,
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.s),
            if (!product.isActive)
              InfoPill(
                label: product.status.label.toUpperCase(),
                background: AppColors.surfaceAlt,
                foreground: AppColors.textMuted,
              )
            else if (warranty != null)
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    daysLeftLabel(warranty.daysLeft),
                    style: AppTextStyles.bodyStrong.copyWith(
                      color: warranty.daysLeft <= 30
                          ? AppColors.warning
                          : AppColors.text,
                    ),
                  ),
                  Text(
                    'garanti',
                    style: AppTextStyles.caption.copyWith(
                      color: AppColors.textSubtle,
                    ),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}
