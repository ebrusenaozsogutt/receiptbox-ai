import '../../transactions/domain/purchase_models.dart';
import '../../transactions/domain/spending_category.dart';

DateTime _day(String iso) {
  final parts = iso.split('-').map(int.parse).toList();
  return DateTime(parts[0], parts[1], parts[2]);
}

DateTime? _dayOrNull(Object? iso) => iso == null ? null : _day(iso as String);

enum ProductStatus {
  active('ACTIVE', 'Aktif'),
  returned('RETURNED', 'İade edildi'),
  archived('ARCHIVED', 'Arşivde');

  const ProductStatus(this.key, this.label);

  final String key;
  final String label;

  static ProductStatus fromKey(String? key) => values.firstWhere(
    (s) => s.key == key,
    orElse: () => ProductStatus.active,
  );
}

/// Where a warranty end comes from (spec 10.2). Always shown next to the date.
enum WarrantySource {
  legalDefault(
    'LEGAL_DEFAULT',
    'Yasal asgari süre (2 yıl) — düzenleyebilirsin',
  ),
  document('DOCUMENT', 'Garanti belgesinden'),
  user('USER', 'Senin girdiğin tarih');

  const WarrantySource(this.key, this.label);

  final String key;
  final String label;

  static WarrantySource fromKey(String? key) =>
      values.firstWhere((s) => s.key == key, orElse: () => WarrantySource.user);
}

enum ReturnSource {
  legalDefault(
    'LEGAL_DEFAULT',
    'Mesafeli satışta cayma hakkı (14 gün) — teslimden sayılır, düzenleyebilirsin',
  ),
  storePolicy('STORE_POLICY', 'Mağazanın iade süresi'),
  user('USER', 'Senin girdiğin tarih');

  const ReturnSource(this.key, this.label);

  final String key;
  final String label;

  static ReturnSource fromKey(String? key) =>
      values.firstWhere((s) => s.key == key, orElse: () => ReturnSource.user);
}

enum ReturnStatus {
  open('OPEN', 'Açık'),
  closed('CLOSED', 'Süresi doldu'),
  returned('RETURNED', 'İade edildi');

  const ReturnStatus(this.key, this.label);

  final String key;
  final String label;

  static ReturnStatus fromKey(String? key) =>
      values.firstWhere((s) => s.key == key, orElse: () => ReturnStatus.open);
}

class Warranty {
  const Warranty({
    required this.startDate,
    required this.endDate,
    required this.source,
    required this.confirmed,
    required this.daysLeft,
  });

  final DateTime? startDate;
  final DateTime endDate;
  final WarrantySource source;

  /// False while the 2-year default was neither accepted nor edited.
  final bool confirmed;
  final int daysLeft;

  factory Warranty.fromJson(Map<String, dynamic> json) => Warranty(
    startDate: _dayOrNull(json['start_date']),
    endDate: _day(json['end_date'] as String),
    source: WarrantySource.fromKey(json['source'] as String?),
    confirmed: json['confirmed'] as bool? ?? false,
    daysLeft: json['days_left'] as int,
  );
}

class ReturnWindow {
  const ReturnWindow({
    required this.endDate,
    required this.source,
    required this.status,
    required this.daysLeft,
  });

  final DateTime endDate;
  final ReturnSource source;
  final ReturnStatus status;
  final int daysLeft;

  factory ReturnWindow.fromJson(Map<String, dynamic> json) => ReturnWindow(
    endDate: _day(json['end_date'] as String),
    source: ReturnSource.fromKey(json['source'] as String?),
    status: ReturnStatus.fromKey(json['status'] as String?),
    daysLeft: json['days_left'] as int,
  );
}

/// A tracked product (backend `ProductOut` / `ProductDetail`).
class Product {
  const Product({
    required this.id,
    required this.transactionId,
    required this.name,
    required this.brand,
    required this.model,
    required this.serialNumber,
    required this.category,
    required this.purchaseDate,
    required this.priceMinor,
    required this.status,
    required this.merchant,
    required this.channel,
    required this.warranty,
    required this.returnWindow,
    required this.documentCount,
    this.financingCostMinor,
    this.refundableMinor,
    this.documents = const [],
  });

  final String id;
  final String? transactionId;
  final String name;
  final String? brand;
  final String? model;
  final String? serialNumber;
  final SpendingCategory? category;
  final DateTime? purchaseDate;

  /// Null = unknown (never shown as 0).
  final int? priceMinor;
  final ProductStatus status;
  final String? merchant;
  final PurchaseChannel? channel;
  final Warranty? warranty;
  final ReturnWindow? returnWindow;
  final int documentCount;

  /// Detail only: installments above the purchase total, what can still be refunded, the files.
  final int? financingCostMinor;
  final int? refundableMinor;
  final List<DocumentInfo> documents;

  bool get isActive => status == ProductStatus.active;

  factory Product.fromJson(Map<String, dynamic> json) => Product(
    id: json['id'] as String,
    transactionId: json['transaction_id'] as String?,
    name: json['name'] as String,
    brand: json['brand'] as String?,
    model: json['model'] as String?,
    serialNumber: json['serial_number'] as String?,
    category: SpendingCategory.fromKey(json['category_key'] as String?),
    purchaseDate: _dayOrNull(json['purchase_date']),
    priceMinor: json['purchase_price_minor'] as int?,
    status: ProductStatus.fromKey(json['status'] as String?),
    merchant: json['merchant_display'] as String?,
    channel: json['channel'] == null
        ? null
        : PurchaseChannel.fromKey(json['channel'] as String?),
    warranty: json['warranty'] == null
        ? null
        : Warranty.fromJson(json['warranty'] as Map<String, dynamic>),
    returnWindow: json['return_window'] == null
        ? null
        : ReturnWindow.fromJson(json['return_window'] as Map<String, dynamic>),
    documentCount: json['document_count'] as int? ?? 0,
    financingCostMinor: json['financing_cost_minor'] as int?,
    refundableMinor: json['refundable_minor'] as int?,
    documents: [
      for (final d in json['documents'] as List<dynamic>? ?? const [])
        DocumentInfo.fromJson(d as Map<String, dynamic>),
    ],
  );
}

/// "Bunu ürün olarak takip edelim mi?": a purchase (or one line of its receipt) worth tracking.
class ProductSuggestion {
  const ProductSuggestion({
    required this.transactionId,
    required this.receiptItemId,
    required this.name,
    required this.merchant,
    required this.category,
    required this.purchaseDate,
    required this.priceMinor,
  });

  final String transactionId;
  final String? receiptItemId;
  final String name;
  final String merchant;
  final SpendingCategory? category;
  final DateTime purchaseDate;
  final int priceMinor;

  factory ProductSuggestion.fromJson(Map<String, dynamic> json) =>
      ProductSuggestion(
        transactionId: json['transaction_id'] as String,
        receiptItemId: json['receipt_item_id'] as String?,
        name: json['name'] as String,
        merchant: json['merchant_display'] as String,
        category: SpendingCategory.fromKey(json['category_key'] as String?),
        purchaseDate: _day(json['purchase_date'] as String),
        priceMinor: json['price_minor'] as int,
      );
}

/// What the "new product" form sends (by hand, or from a purchase / receipt line).
class ProductInput {
  const ProductInput({
    this.transactionId,
    this.receiptItemId,
    this.name,
    this.brand,
    this.model,
    this.serialNumber,
    this.category,
    this.purchaseDate,
    this.priceMinor,
    this.channel,
  });

  final String? transactionId;
  final String? receiptItemId;
  final String? name;
  final String? brand;
  final String? model;
  final String? serialNumber;
  final SpendingCategory? category;
  final DateTime? purchaseDate;
  final int? priceMinor;
  final PurchaseChannel? channel;

  Map<String, dynamic> toJson() => {
    'transaction_id': ?transactionId,
    'receipt_item_id': ?receiptItemId,
    if (name != null && name!.trim().isNotEmpty) 'name': name!.trim(),
    if (brand != null && brand!.trim().isNotEmpty) 'brand': brand!.trim(),
    if (model != null && model!.trim().isNotEmpty) 'model': model!.trim(),
    if (serialNumber != null && serialNumber!.trim().isNotEmpty)
      'serial_number': serialNumber!.trim(),
    if (category != null) 'category_key': category!.key,
    if (purchaseDate != null) 'purchase_date': dateToApi(purchaseDate!),
    'purchase_price_minor': ?priceMinor,
    if (channel != null) 'channel': channel!.key,
  };
}

/// A bank CREDIT row and the purchases it may refund (suggestion only).
class RefundSuggestion {
  const RefundSuggestion({
    required this.observationId,
    required this.merchant,
    required this.amountMinor,
    required this.date,
    required this.candidates,
  });

  final String observationId;
  final String merchant;
  final int amountMinor;
  final DateTime date;
  final List<RefundCandidate> candidates;

  factory RefundSuggestion.fromJson(Map<String, dynamic> json) =>
      RefundSuggestion(
        observationId: json['observation_id'] as String,
        merchant: json['merchant_raw'] as String? ?? '',
        amountMinor: json['amount_minor'] as int,
        date: _day(json['obs_date'] as String),
        candidates: [
          for (final c in json['candidates'] as List<dynamic>)
            RefundCandidate.fromJson(c as Map<String, dynamic>),
        ],
      );
}

class RefundCandidate {
  const RefundCandidate({
    required this.transactionId,
    required this.merchant,
    required this.purchaseDate,
    required this.totalMinor,
    required this.refundableMinor,
  });

  final String transactionId;
  final String merchant;
  final DateTime purchaseDate;
  final int totalMinor;
  final int refundableMinor;

  factory RefundCandidate.fromJson(Map<String, dynamic> json) =>
      RefundCandidate(
        transactionId: json['transaction_id'] as String,
        merchant: json['merchant_display'] as String,
        purchaseDate: _day(json['purchase_date'] as String),
        totalMinor: json['total_minor'] as int,
        refundableMinor: json['refundable_minor'] as int,
      );
}
