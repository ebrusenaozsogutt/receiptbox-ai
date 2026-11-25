import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../domain/product_models.dart';
import 'products_api.dart';

part 'products_providers.g.dart';

/// Every product of the user (the Products tab filters them on the phone).
@riverpod
Future<List<Product>> productList(Ref ref) =>
    ref.watch(productsApiProvider).list();

@riverpod
Future<Product> productDetail(Ref ref, String id) =>
    ref.watch(productsApiProvider).detail(id);

/// "Öneriler": purchases worth tracking as products.
@riverpod
Future<List<ProductSuggestion>> productSuggestions(Ref ref) =>
    ref.watch(productsApiProvider).suggestions();

/// P12: the bank CREDIT rows that wait, with the purchases they may refund.
@riverpod
Future<List<RefundSuggestion>> refundSuggestions(Ref ref) =>
    ref.watch(productsApiProvider).refundSuggestions();

/// The Products tab filter chips.
enum ProductFilter {
  all('Tümü'),
  active('Aktif'),
  returned('İade edildi'),
  archived('Arşiv');

  const ProductFilter(this.label);

  final String label;

  bool matches(Product product) => switch (this) {
    ProductFilter.all => true,
    ProductFilter.active => product.status == ProductStatus.active,
    ProductFilter.returned => product.status == ProductStatus.returned,
    ProductFilter.archived => product.status == ProductStatus.archived,
  };
}

@riverpod
class ProductFilterController extends _$ProductFilterController {
  @override
  ProductFilter build() => ProductFilter.all;

  void set(ProductFilter filter) => state = filter;
}
