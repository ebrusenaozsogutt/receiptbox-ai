import 'package:receiptbox/core/networking/api_error.dart';
import 'package:receiptbox/features/products/data/products_api.dart';
import 'package:receiptbox/features/products/domain/product_models.dart';
import 'package:receiptbox/features/transactions/domain/purchase_models.dart';
import 'package:receiptbox/features/transactions/domain/spending_category.dart';

/// A product as the backend answers it (defaults: an online TV bought on 10 November 2026).
Product fakeProduct({
  String id = 'p-1',
  String name = 'Samsung TV',
  String? transactionId = 'tx-1',
  SpendingCategory category = SpendingCategory.technology,
  ProductStatus status = ProductStatus.active,
  int? priceMinor = 1249900,
  Warranty? warranty,
  ReturnWindow? returnWindow,
  bool noWarranty = false,
  bool noReturn = false,
  PurchaseChannel channel = PurchaseChannel.online,
  int? financingCostMinor,
  int? refundableMinor = 1249900,
  List<DocumentInfo> documents = const [],
}) => Product(
  id: id,
  transactionId: transactionId,
  name: name,
  brand: null,
  model: null,
  serialNumber: null,
  category: category,
  purchaseDate: DateTime(2026, 11, 10),
  priceMinor: priceMinor,
  status: status,
  merchant: 'Teknosa',
  channel: channel,
  warranty: noWarranty
      ? null
      : warranty ??
            Warranty(
              startDate: DateTime(2026, 11, 10),
              endDate: DateTime(2028, 11, 10),
              source: WarrantySource.legalDefault,
              confirmed: false,
              daysLeft: 721,
            ),
  returnWindow: noReturn
      ? null
      : returnWindow ??
            ReturnWindow(
              endDate: DateTime(2026, 11, 24),
              source: ReturnSource.legalDefault,
              status: ReturnStatus.open,
              daysLeft: 4,
            ),
  documentCount: documents.length,
  financingCostMinor: financingCostMinor,
  refundableMinor: refundableMinor,
  documents: documents,
);

/// The products endpoints in memory. Tests fill [products] / [suggestionAnswer] and read back
/// what the app sent.
class FakeProductsApi implements ProductsApi {
  final List<Product> products = [];
  List<ProductSuggestion> suggestionAnswer = [];
  List<RefundSuggestion> refundSuggestionAnswer = [];
  final created = <ProductInput>[];
  final patches = <({String id, Map<String, dynamic> fields})>[];
  final warranties = <({String id, DateTime end, WarrantySource source})>[];
  final returns = <({String id, DateTime end, ReturnSource source})>[];
  final dismissed = <ProductSuggestion>[];
  final refunds =
      <
        ({
          String transactionId,
          int amountMinor,
          DateTime date,
          String? productId,
        })
      >[];
  final linked = <({String observationId, String transactionId})>[];
  ApiError? error;

  /// What refund / linkRefund answer with.
  PurchaseDetail? refundAnswer;

  Product _find(String id) => products.firstWhere((p) => p.id == id);

  void _check() {
    final e = error;
    if (e != null) throw e;
  }

  @override
  Future<List<Product>> list() async {
    _check();
    return [...products];
  }

  @override
  Future<Product> detail(String id) async {
    _check();
    return _find(id);
  }

  @override
  Future<Product> create(ProductInput input) async {
    _check();
    created.add(input);
    final product = fakeProduct(
      id: 'p-${products.length + 1}',
      name: input.name ?? 'Yeni ürün',
      transactionId: input.transactionId,
    );
    products.add(product);
    return product;
  }

  @override
  Future<Product> patch(String id, Map<String, dynamic> fields) async {
    _check();
    patches.add((id: id, fields: fields));
    return _find(id);
  }

  @override
  Future<void> delete(String id) async {
    _check();
    products.removeWhere((p) => p.id == id);
  }

  @override
  Future<Product> putWarranty(
    String id, {
    required DateTime endDate,
    required WarrantySource source,
  }) async {
    _check();
    warranties.add((id: id, end: endDate, source: source));
    return _find(id);
  }

  @override
  Future<Product> putReturnWindow(
    String id, {
    required DateTime endDate,
    required ReturnSource source,
  }) async {
    _check();
    returns.add((id: id, end: endDate, source: source));
    return _find(id);
  }

  @override
  Future<List<ProductSuggestion>> suggestions() async {
    _check();
    return [...suggestionAnswer];
  }

  @override
  Future<void> dismiss(ProductSuggestion suggestion) async {
    _check();
    dismissed.add(suggestion);
    suggestionAnswer = [
      for (final s in suggestionAnswer)
        if (s.transactionId != suggestion.transactionId) s,
    ];
  }

  @override
  Future<PurchaseDetail> refund(
    String transactionId, {
    required int amountMinor,
    required DateTime date,
    String? productId,
  }) async {
    _check();
    refunds.add((
      transactionId: transactionId,
      amountMinor: amountMinor,
      date: date,
      productId: productId,
    ));
    return refundAnswer!;
  }

  @override
  Future<List<RefundSuggestion>> refundSuggestions() async {
    _check();
    return [...refundSuggestionAnswer];
  }

  @override
  Future<PurchaseDetail> linkRefund(
    String observationId,
    String transactionId,
  ) async {
    _check();
    linked.add((observationId: observationId, transactionId: transactionId));
    refundSuggestionAnswer = [
      for (final s in refundSuggestionAnswer)
        if (s.observationId != observationId) s,
    ];
    return refundAnswer!;
  }
}
