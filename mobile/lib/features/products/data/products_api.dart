import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/networking/dio_provider.dart';
import '../../transactions/domain/purchase_models.dart';
import '../domain/product_models.dart';

part 'products_api.g.dart';

/// Products, warranties, return windows and refunds (backend P12).
abstract interface class ProductsApi {
  Future<List<Product>> list();

  Future<Product> detail(String id);

  Future<Product> create(ProductInput input);

  /// Fields to change (backend `ProductPatch`), e.g. `{'status': 'ARCHIVED'}`.
  Future<Product> patch(String id, Map<String, dynamic> fields);

  Future<void> delete(String id);

  /// Accept the 2-year default (same date, LEGAL_DEFAULT) or enter another end.
  Future<Product> putWarranty(
    String id, {
    required DateTime endDate,
    required WarrantySource source,
  });

  Future<Product> putReturnWindow(
    String id, {
    required DateTime endDate,
    required ReturnSource source,
  });

  Future<List<ProductSuggestion>> suggestions();

  /// "Hayır, bir daha sorma".
  Future<void> dismiss(ProductSuggestion suggestion);

  /// "İade edildi": full or partial; answers the purchase with its refunds.
  Future<PurchaseDetail> refund(
    String transactionId, {
    required int amountMinor,
    required DateTime date,
    String? productId,
  });

  Future<List<RefundSuggestion>> refundSuggestions();

  /// The user's answer: this bank CREDIT row is a refund of that purchase.
  Future<PurchaseDetail> linkRefund(String observationId, String transactionId);
}

class DioProductsApi implements ProductsApi {
  const DioProductsApi(this._dio);

  final Dio _dio;

  Future<T> _guard<T>(Future<T> Function() call) async {
    try {
      return await call();
    } on Object catch (error) {
      throw apiErrorFrom(error);
    }
  }

  @override
  Future<List<Product>> list() => _guard(() async {
    final response = await _dio.get<Map<String, dynamic>>('/products');
    return [
      for (final p in response.data!['items'] as List<dynamic>)
        Product.fromJson(p as Map<String, dynamic>),
    ];
  });

  @override
  Future<Product> detail(String id) => _guard(() async {
    final response = await _dio.get<Map<String, dynamic>>('/products/$id');
    return Product.fromJson(response.data!);
  });

  @override
  Future<Product> create(ProductInput input) => _guard(() async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/products',
      data: input.toJson(),
    );
    return Product.fromJson(response.data!);
  });

  @override
  Future<Product> patch(String id, Map<String, dynamic> fields) =>
      _guard(() async {
        final response = await _dio.patch<Map<String, dynamic>>(
          '/products/$id',
          data: fields,
        );
        return Product.fromJson(response.data!);
      });

  @override
  Future<void> delete(String id) => _guard(() async {
    await _dio.delete<void>('/products/$id');
  });

  @override
  Future<Product> putWarranty(
    String id, {
    required DateTime endDate,
    required WarrantySource source,
  }) => _guard(() async {
    final response = await _dio.put<Map<String, dynamic>>(
      '/products/$id/warranty',
      data: {'end_date': dateToApi(endDate), 'source': source.key},
    );
    return Product.fromJson(response.data!);
  });

  @override
  Future<Product> putReturnWindow(
    String id, {
    required DateTime endDate,
    required ReturnSource source,
  }) => _guard(() async {
    final response = await _dio.put<Map<String, dynamic>>(
      '/products/$id/return-window',
      data: {'end_date': dateToApi(endDate), 'source': source.key},
    );
    return Product.fromJson(response.data!);
  });

  @override
  Future<List<ProductSuggestion>> suggestions() => _guard(() async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/products/suggestions',
    );
    return [
      for (final s in response.data!['items'] as List<dynamic>)
        ProductSuggestion.fromJson(s as Map<String, dynamic>),
    ];
  });

  @override
  Future<void> dismiss(ProductSuggestion suggestion) => _guard(() async {
    await _dio.post<void>(
      '/products/suggestions/dismiss',
      data: {
        'transaction_id': suggestion.transactionId,
        'receipt_item_id': ?suggestion.receiptItemId,
      },
    );
  });

  @override
  Future<PurchaseDetail> refund(
    String transactionId, {
    required int amountMinor,
    required DateTime date,
    String? productId,
  }) => _guard(() async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/transactions/$transactionId/refund',
      data: {
        'amount_minor': amountMinor,
        'date': dateToApi(date),
        'product_id': ?productId,
      },
    );
    return PurchaseDetail.fromJson(response.data!);
  });

  @override
  Future<List<RefundSuggestion>> refundSuggestions() => _guard(() async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/refunds/suggestions',
    );
    return [
      for (final s in response.data!['items'] as List<dynamic>)
        RefundSuggestion.fromJson(s as Map<String, dynamic>),
    ];
  });

  @override
  Future<PurchaseDetail> linkRefund(
    String observationId,
    String transactionId,
  ) => _guard(() async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/observations/$observationId/link-refund',
      data: {'transaction_id': transactionId},
    );
    return PurchaseDetail.fromJson(response.data!);
  });
}

@Riverpod(keepAlive: true)
ProductsApi productsApi(Ref ref) => DioProductsApi(ref.watch(dioProvider));
