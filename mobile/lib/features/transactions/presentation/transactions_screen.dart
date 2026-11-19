import 'dart:async';

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
import '../../capture/presentation/review/review_widgets.dart';
import '../data/transactions_providers.dart';
import '../domain/purchase_models.dart';
import '../domain/spending_category.dart';

/// "Harcamalar": every saved purchase, newest first, grouped by day, with filters and search.
class TransactionsScreen extends ConsumerStatefulWidget {
  const TransactionsScreen({super.key});

  @override
  ConsumerState<TransactionsScreen> createState() => _TransactionsScreenState();
}

class _TransactionsScreenState extends ConsumerState<TransactionsScreen> {
  final _search = TextEditingController();
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _onSearchChanged(String text) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 400), () {
      final filter = ref.read(purchaseFilterControllerProvider);
      ref
          .read(purchaseFilterControllerProvider.notifier)
          .set(filter.copyWith(search: text.trim()));
    });
  }

  Future<void> _pickCategory() async {
    final filter = ref.read(purchaseFilterControllerProvider);
    final picked = await pickCategoryFilter(context, filter.category);
    if (!mounted || picked == null) return;
    ref
        .read(purchaseFilterControllerProvider.notifier)
        .set(filter.copyWith(category: () => picked.category));
  }

  Future<void> _pickRange() async {
    final filter = ref.read(purchaseFilterControllerProvider);
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(2000),
      lastDate: DateTime.now().add(const Duration(days: 1)),
      initialDateRange: filter.from != null && filter.to != null
          ? DateTimeRange(start: filter.from!, end: filter.to!)
          : null,
      locale: const Locale('tr', 'TR'),
    );
    if (!mounted || picked == null) return;
    ref
        .read(purchaseFilterControllerProvider.notifier)
        .set(filter.copyWith(from: () => picked.start, to: () => picked.end));
  }

  @override
  Widget build(BuildContext context) {
    final filter = ref.watch(purchaseFilterControllerProvider);
    final list = ref.watch(purchaseListProvider);
    return SafeArea(
      child: Column(
        children: [
          ScreenHeader(
            title: 'Harcamalar',
            actions: [
              IconButton(
                key: const Key('add_manual_button'),
                tooltip: 'Manuel harcama ekle',
                icon: const Icon(Icons.add, color: AppColors.primary),
                onPressed: () => context.push('/transactions/new'),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.screenH),
            child: TextField(
              key: const Key('search_field'),
              controller: _search,
              onChanged: _onSearchChanged,
              textInputAction: TextInputAction.search,
              decoration: const InputDecoration(
                hintText: 'Mağaza veya not ara',
                prefixIcon: Icon(Icons.search),
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.s),
          SizedBox(
            height: AppSizes.minTapTarget,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.screenH,
              ),
              children: [
                _FilterChip(
                  key: const Key('filter_category'),
                  label: filter.category?.label ?? 'Kategori',
                  active: filter.category != null,
                  onTap: _pickCategory,
                ),
                const SizedBox(width: AppSpacing.s),
                _FilterChip(
                  key: const Key('filter_date'),
                  label: filter.from == null
                      ? 'Tarih'
                      : '${formatDateTr(filter.from!)} – ${formatDateTr(filter.to!)}',
                  active: filter.from != null,
                  onTap: _pickRange,
                ),
                if (filter.isActive) ...[
                  const SizedBox(width: AppSpacing.s),
                  _FilterChip(
                    key: const Key('filter_clear'),
                    label: 'Temizle',
                    active: false,
                    icon: Icons.close,
                    onTap: () {
                      _search.clear();
                      ref
                          .read(purchaseFilterControllerProvider.notifier)
                          .clear();
                    },
                  ),
                ],
              ],
            ),
          ),
          Expanded(
            child: list.when(
              loading: () => const LoadingView(),
              error: (error, _) => ErrorView(
                message: error is ApiError
                    ? error.message
                    : 'Harcamalar yüklenemedi.',
                onRetry: () => ref.invalidate(purchaseListProvider),
              ),
              data: (state) => _Body(state: state, filtered: filter.isActive),
            ),
          ),
        ],
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    super.key,
    required this.label,
    required this.active,
    required this.onTap,
    this.icon,
  });

  final String label;
  final bool active;
  final VoidCallback onTap;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Material(
        color: active ? AppColors.primarySoft : AppColors.surface,
        shape: StadiumBorder(
          side: BorderSide(
            color: active ? AppColors.primary : AppColors.border,
          ),
        ),
        child: InkWell(
          customBorder: const StadiumBorder(),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.m,
              vertical: AppSpacing.s,
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (icon != null) ...[
                  Icon(icon, size: AppSizes.iconS),
                  const SizedBox(width: AppSpacing.xxs),
                ],
                Text(
                  label,
                  style: AppTextStyles.label.copyWith(
                    color: active ? AppColors.primary : AppColors.text,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A day header or a purchase, in the order they are shown.
sealed class _Entry {
  const _Entry();
}

class _DayHeader extends _Entry {
  const _DayHeader(this.date);
  final DateTime date;
}

class _PurchaseEntry extends _Entry {
  const _PurchaseEntry(this.purchase);
  final Purchase purchase;
}

List<_Entry> _group(List<Purchase> purchases) {
  final entries = <_Entry>[];
  DateTime? current;
  for (final purchase in purchases) {
    if (current == null || current != purchase.date) {
      current = purchase.date;
      entries.add(_DayHeader(current));
    }
    entries.add(_PurchaseEntry(purchase));
  }
  return entries;
}

class _Body extends ConsumerWidget {
  const _Body({required this.state, required this.filtered});

  final PurchaseListState state;
  final bool filtered;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (state.items.isEmpty) {
      return RefreshIndicator(
        onRefresh: () => ref.refresh(purchaseListProvider.future),
        child: ListView(
          children: [
            SizedBox(
              height: AppSizes.resultTextMaxHeight,
              child: EmptyState(
                icon: Icons.receipt_long_outlined,
                title: filtered
                    ? 'Bu filtreye uyan harcama yok'
                    : 'Henüz harcama yok',
                message: filtered
                    ? 'Filtreleri değiştirmeyi dene.'
                    : 'Fiş, e-fatura ekle ya da elle bir harcama gir; burada görünür.',
              ),
            ),
          ],
        ),
      );
    }
    final entries = _group(state.items);
    return RefreshIndicator(
      onRefresh: () => ref.refresh(purchaseListProvider.future),
      child: ListView.builder(
        key: const Key('purchase_list'),
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.screenH,
          AppSpacing.none,
          AppSpacing.screenH,
          AppSpacing.xxl,
        ),
        itemCount: entries.length + 2,
        itemBuilder: (context, index) {
          if (index == 0) return _Totals(state: state, filtered: filtered);
          if (index == entries.length + 1) return _MoreFooter(state: state);
          return switch (entries[index - 1]) {
            _DayHeader(:final date) => Padding(
              padding: const EdgeInsets.only(
                top: AppSpacing.l,
                bottom: AppSpacing.s,
              ),
              child: Text(
                formatDateTr(date),
                style: AppTextStyles.label.copyWith(color: AppColors.textMuted),
              ),
            ),
            _PurchaseEntry(:final purchase) => _PurchaseRow(purchase: purchase),
          };
        },
      ),
    );
  }
}

class _Totals extends StatelessWidget {
  const _Totals({required this.state, required this.filtered});

  final PurchaseListState state;
  final bool filtered;

  @override
  Widget build(BuildContext context) {
    return Padding(
      key: const Key('purchase_totals'),
      padding: const EdgeInsets.only(top: AppSpacing.s),
      child: Row(
        children: [
          Expanded(
            child: Text(
              filtered ? 'Filtreye uyan ${state.count} harcama' : '${state.count} harcama',
              style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
            ),
          ),
          Text(formatMoneyTl(state.sumMinor), style: AppTextStyles.bodyStrong),
        ],
      ),
    );
  }
}

class _MoreFooter extends ConsumerWidget {
  const _MoreFooter({required this.state});

  final PurchaseListState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (state.loadingMore) {
      return const Padding(
        padding: EdgeInsets.all(AppSpacing.l),
        child: LoadingView(),
      );
    }
    if (!state.hasMore) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.m),
      child: OutlinedButton(
        key: const Key('load_more'),
        onPressed: () => ref.read(purchaseListProvider.notifier).loadMore(),
        child: Text(
          state.moreFailed ? 'Yüklenemedi, tekrar dene' : 'Daha fazla göster',
        ),
      ),
    );
  }
}

class _PurchaseRow extends StatelessWidget {
  const _PurchaseRow({required this.purchase});

  final Purchase purchase;

  @override
  Widget build(BuildContext context) {
    final category = purchase.category ?? SpendingCategory.other;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.s),
      child: Material(
        color: AppColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: AppRadius.card,
          side: const BorderSide(color: AppColors.border),
        ),
        child: InkWell(
          key: Key('purchase_${purchase.id}'),
          customBorder: RoundedRectangleBorder(borderRadius: AppRadius.card),
          onTap: () => context.push('/transactions/${purchase.id}'),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.l),
            child: Row(
              children: [
                CategoryDot(color: category.color),
                const SizedBox(width: AppSpacing.m),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        purchase.merchant,
                        style: AppTextStyles.bodyStrong,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      Text(
                        category.label,
                        style: AppTextStyles.bodyS.copyWith(
                          color: AppColors.textMuted,
                        ),
                      ),
                    ],
                  ),
                ),
                if (purchase.documentCount > 0)
                  const Padding(
                    padding: EdgeInsets.only(right: AppSpacing.s),
                    child: Icon(
                      Icons.attach_file,
                      size: AppSizes.iconS,
                      color: AppColors.textSubtle,
                    ),
                  ),
                Text(
                  formatMoneyTl(purchase.totalMinor),
                  style: AppTextStyles.bodyStrong,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
