import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../domain/purchase_models.dart';
import '../domain/spending_category.dart';
import 'transactions_api.dart';

part 'transactions_providers.g.dart';

/// What the list screen filters by. A null field means "no filter".
class PurchaseFilter {
  const PurchaseFilter({this.from, this.to, this.category, this.search = ''});

  final DateTime? from;
  final DateTime? to;
  final SpendingCategory? category;
  final String search;

  bool get isActive =>
      from != null || to != null || category != null || search.isNotEmpty;

  PurchaseFilter copyWith({
    DateTime? Function()? from,
    DateTime? Function()? to,
    SpendingCategory? Function()? category,
    String? search,
  }) => PurchaseFilter(
    from: from != null ? from() : this.from,
    to: to != null ? to() : this.to,
    category: category != null ? category() : this.category,
    search: search ?? this.search,
  );
}

@riverpod
class PurchaseFilterController extends _$PurchaseFilterController {
  @override
  PurchaseFilter build() => const PurchaseFilter();

  void set(PurchaseFilter filter) => state = filter;
  void clear() => state = const PurchaseFilter();
}

/// The pages loaded so far, and the totals of everything that matches the filters.
class PurchaseListState {
  const PurchaseListState({
    required this.items,
    required this.count,
    required this.sumMinor,
    this.loadingMore = false,
    this.moreFailed = false,
  });

  final List<Purchase> items;
  final int count;
  final int sumMinor;
  final bool loadingMore;
  final bool moreFailed;

  bool get hasMore => items.length < count;

  PurchaseListState copyWith({
    List<Purchase>? items,
    bool? loadingMore,
    bool? moreFailed,
  }) => PurchaseListState(
    items: items ?? this.items,
    count: count,
    sumMinor: sumMinor,
    loadingMore: loadingMore ?? this.loadingMore,
    moreFailed: moreFailed ?? this.moreFailed,
  );
}

const purchasePageSize = 30;

/// The purchase list for the current filter. Changing the filter or calling `ref.invalidate`
/// loads the first page again.
@riverpod
class PurchaseList extends _$PurchaseList {
  @override
  Future<PurchaseListState> build() async {
    final filter = ref.watch(purchaseFilterControllerProvider);
    final page = await _load(filter, 0);
    return PurchaseListState(
      items: page.items,
      count: page.count,
      sumMinor: page.sumMinor,
    );
  }

  Future<PurchasePage> _load(PurchaseFilter filter, int offset) =>
      ref
          .read(transactionsApiProvider)
          .list(
            from: filter.from,
            to: filter.to,
            category: filter.category,
            search: filter.search,
            limit: purchasePageSize,
            offset: offset,
          );

  Future<void> loadMore() async {
    final current = state.value;
    if (current == null || current.loadingMore || !current.hasMore) return;
    state = AsyncData(current.copyWith(loadingMore: true, moreFailed: false));
    try {
      final page = await _load(
        ref.read(purchaseFilterControllerProvider),
        current.items.length,
      );
      if (!ref.mounted) return;
      state = AsyncData(
        current.copyWith(
          items: [...current.items, ...page.items],
          loadingMore: false,
        ),
      );
    } on Object {
      if (!ref.mounted) return;
      state = AsyncData(
        current.copyWith(loadingMore: false, moreFailed: true),
      );
    }
  }
}

/// One purchase with its evidence, lines and documents.
@riverpod
Future<PurchaseDetail> purchaseDetail(Ref ref, String id) =>
    ref.watch(transactionsApiProvider).detail(id);
