import 'package:material_ui/material_ui.dart' show TimeOfDay;

import '../../installments/domain/installment_models.dart';
import '../../products/domain/product_models.dart';
import 'spending_category.dart';

DateTime _day(String iso) {
  final parts = iso.split('-').map(int.parse).toList();
  return DateTime(parts[0], parts[1], parts[2]);
}

TimeOfDay? _time(String? text) {
  if (text == null || text.isEmpty) return null;
  final parts = text.split(':');
  return TimeOfDay(hour: int.parse(parts[0]), minute: int.parse(parts[1]));
}

/// "18:42" for the screen.
String timeLabel(TimeOfDay time) =>
    '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';

/// "18:42:00" for the API.
String timeToApi(TimeOfDay time) =>
    '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}:00';

/// "2026-11-14" for the API.
String dateToApi(DateTime date) =>
    '${date.year.toString().padLeft(4, '0')}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';

/// A purchase as shown in the list (and the head of the detail screen). Money is kuruş.
class Purchase {
  const Purchase({
    required this.id,
    required this.merchant,
    required this.category,
    required this.date,
    required this.time,
    required this.totalMinor,
    required this.channel,
    required this.note,
    required this.documentCount,
    this.isEstimated = false,
    this.isInstallment = false,
    this.refundedMinor = 0,
    this.isRefund = false,
  });

  final String id;
  final String merchant;
  final SpendingCategory? category;
  final DateTime date;
  final TimeOfDay? time;
  final int totalMinor;
  final PurchaseChannel channel;
  final String? note;
  final int documentCount;

  /// P10: made from a bank installment row, not from a receipt ("tahmini"). A receipt that comes
  /// later merges with it and corrects it.
  final bool isEstimated;

  /// Paid in installments (it has, or had, a plan).
  final bool isInstallment;

  /// P12: the sum of this purchase's refunds; the list and the totals count it net.
  final int refundedMinor;

  /// P12: a refund that belongs to no purchase (refunds of a purchase are shown on it).
  final bool isRefund;

  /// What is left after the refunds.
  int get netMinor => totalMinor - refundedMinor;

  factory Purchase.fromJson(Map<String, dynamic> json) => Purchase(
    id: json['id'] as String,
    merchant: json['merchant_display'] as String,
    category: SpendingCategory.fromKey(json['category_key'] as String?),
    date: _day(json['purchase_date'] as String),
    time: _time(json['purchase_time'] as String?),
    totalMinor: json['total_minor'] as int,
    channel: PurchaseChannel.fromKey(json['channel'] as String?),
    note: json['note'] as String?,
    documentCount: json['document_count'] as int? ?? 0,
    isEstimated: json['is_estimated'] as bool? ?? false,
    isInstallment: json['payment_type'] == 'INSTALLMENT',
    refundedMinor: json['refunded_minor'] as int? ?? 0,
    isRefund: json['kind'] == 'REFUND',
  );
}

/// One page of the list, plus the net total of everything that matches the filters.
class PurchasePage {
  const PurchasePage({
    required this.items,
    required this.count,
    required this.sumMinor,
  });

  final List<Purchase> items;
  final int count;
  final int sumMinor;

  factory PurchasePage.fromJson(Map<String, dynamic> json) => PurchasePage(
    items: [
      for (final item in json['items'] as List<dynamic>)
        Purchase.fromJson(item as Map<String, dynamic>),
    ],
    count: json['count'] as int,
    sumMinor: json['sum_minor'] as int,
  );
}

/// The kind of evidence behind a purchase (chips on the detail screen).
enum EvidenceKind {
  receipt('Fiş'),
  einvoice('e-Fatura'),
  bank('Banka'),
  manual('Manuel');

  const EvidenceKind(this.label);

  final String label;

  static EvidenceKind fromSource(String source) => switch (source) {
    'EINVOICE_QR' => EvidenceKind.einvoice,
    'BANK_SCREENSHOT' => EvidenceKind.bank,
    'MANUAL' => EvidenceKind.manual,
    _ => EvidenceKind.receipt,
  };
}

class ReceiptLine {
  const ReceiptLine({
    required this.name,
    required this.quantity,
    required this.totalMinor,
  });

  final String name;
  final String quantity;
  final int? totalMinor;

  factory ReceiptLine.fromJson(Map<String, dynamic> json) => ReceiptLine(
    name: json['name_raw'] as String,
    quantity: '${json['quantity']}',
    totalMinor: json['total_price_minor'] as int?,
  );
}

class DocumentInfo {
  const DocumentInfo({
    required this.id,
    required this.type,
    required this.mimeType,
  });

  final String id;
  final String type;
  final String mimeType;

  bool get isPdf => mimeType == 'application/pdf';

  // Two documents are the same when their ids are (lets a provider take one as its key).
  @override
  bool operator ==(Object other) => other is DocumentInfo && other.id == id;

  @override
  int get hashCode => id.hashCode;

  factory DocumentInfo.fromJson(Map<String, dynamic> json) => DocumentInfo(
    id: json['id'] as String,
    type: json['type'] as String,
    mimeType: json['mime_type'] as String,
  );
}

/// One record behind a purchase: which one, and what amount it showed (a bank row may differ a
/// little from the receipt total).
class EvidenceItem {
  const EvidenceItem({
    required this.observationId,
    required this.kind,
    required this.amountMinor,
    this.installmentSeq,
    this.installmentCount,
    this.isPayment = false,
  });

  final String observationId;
  final EvidenceKind kind;
  final int? amountMinor;

  /// P10: a bank row `k/n` that is payment k of the purchase. It is evidence of a payment, not
  /// a second record of the purchase, so it cannot be separated ("Ayır").
  final int? installmentSeq;
  final int? installmentCount;
  final bool isPayment;
}

/// How a save ended up on an existing purchase (backend `MergeOut`).
class MergeInfo {
  const MergeInfo({
    required this.decisionId,
    required this.observationId,
    required this.isAuto,
  });

  final String decisionId;

  /// The record that was attached.
  final String observationId;

  /// Merged without asking (score high enough): the app offers "Geri al".
  final bool isAuto;

  factory MergeInfo.fromJson(Map<String, dynamic> json) => MergeInfo(
    decisionId: json['decision_id'] as String,
    observationId: json['observation_id'] as String,
    isAuto: json['decision'] == 'AUTO_ACCEPTED',
  );
}

class PurchaseDetail {
  const PurchaseDetail({
    required this.purchase,
    required this.evidence,
    required this.lines,
    required this.documents,
    this.evidenceItems = const [],
    this.merge,
    this.plan,
    this.refunds = const [],
    this.refundableMinor = 0,
    this.products = const [],
    this.productSuggestions = const [],
  });

  final Purchase purchase;
  final List<EvidenceKind> evidence;
  final List<ReceiptLine> lines;
  final List<DocumentInfo> documents;

  /// The same records as [evidence], with their ids (what "Ayır" needs).
  final List<EvidenceItem> evidenceItems;

  /// Set when this answer is the result of a merge.
  final MergeInfo? merge;

  /// P10: the installment plan, when the purchase is paid in installments.
  final InstallmentPlan? plan;

  /// P12: the refunds of this purchase and what can still be refunded.
  final List<RefundEntry> refunds;
  final int refundableMinor;

  /// P12: the products made from this purchase, and the product suggestions it has.
  final List<ProductBrief> products;
  final List<ProductSuggestion> productSuggestions;

  /// The records that can be separated ("Ayır"): every record except the bank rows that are
  /// installment payments.
  List<EvidenceItem> get mergedRecords => [
    for (final item in evidenceItems)
      if (!item.isPayment) item,
  ];

  /// The bank rows that are payments of the plan (P10).
  List<EvidenceItem> get paymentRows => [
    for (final item in evidenceItems)
      if (item.isPayment) item,
  ];

  /// Two records of one purchase: each can be separated ("Ayır").
  bool get isMerged => mergedRecords.length > 1;

  factory PurchaseDetail.fromJson(Map<String, dynamic> json) => PurchaseDetail(
    purchase: Purchase.fromJson(json),
    evidence: [
      for (final e in json['evidence'] as List<dynamic>)
        EvidenceKind.fromSource(
          (e as Map<String, dynamic>)['source'] as String,
        ),
    ],
    evidenceItems: [
      for (final e in json['evidence'] as List<dynamic>)
        EvidenceItem(
          observationId: (e as Map<String, dynamic>)['id'] as String,
          kind: EvidenceKind.fromSource(e['source'] as String),
          amountMinor: e['amount_minor'] as int?,
          installmentSeq: e['installment_seq'] as int?,
          installmentCount: e['installment_count'] as int?,
          isPayment: e['is_installment_payment'] as bool? ?? false,
        ),
    ],
    merge: json['match'] == null
        ? null
        : MergeInfo.fromJson(json['match'] as Map<String, dynamic>),
    plan: json['plan'] == null
        ? null
        : InstallmentPlan.fromJson(json['plan'] as Map<String, dynamic>),
    refunds: [
      for (final r in json['refunds'] as List<dynamic>? ?? const [])
        RefundEntry.fromJson(r as Map<String, dynamic>),
    ],
    refundableMinor: json['refundable_minor'] as int? ?? 0,
    products: [
      for (final p in json['products'] as List<dynamic>? ?? const [])
        ProductBrief.fromJson(p as Map<String, dynamic>),
    ],
    productSuggestions: [
      for (final p in json['product_suggestions'] as List<dynamic>? ?? const [])
        ProductSuggestion.fromJson(p as Map<String, dynamic>),
    ],
    lines: [
      for (final i in json['items'] as List<dynamic>)
        ReceiptLine.fromJson(i as Map<String, dynamic>),
    ],
    documents: [
      for (final d in json['documents'] as List<dynamic>)
        DocumentInfo.fromJson(d as Map<String, dynamic>),
    ],
  );
}

/// One line of a receipt as the user edited it.
class LineInput {
  const LineInput({required this.name, this.totalMinor});

  final String name;
  final int? totalMinor;

  Map<String, dynamic> toJson() => {
    'name_raw': name,
    if (totalMinor != null) 'total_price_minor': totalMinor,
  };
}

/// What the review screen, the manual form and the edit form send.
class PurchaseInput {
  const PurchaseInput({
    required this.merchant,
    required this.date,
    required this.time,
    required this.totalMinor,
    required this.category,
    required this.channel,
    this.note,
    this.lines = const [],
    this.rememberCategory = false,
    this.installmentCount,
  });

  final String merchant;
  final DateTime date;
  final TimeOfDay? time;
  final int totalMinor;
  final SpendingCategory category;
  final PurchaseChannel channel;
  final String? note;
  final List<LineInput> lines;
  final bool rememberCategory;

  /// "Taksitli": how many installments (2-36), or null when the purchase is not paid in
  /// installments. Only sent when a purchase is created or confirmed.
  final int? installmentCount;

  Map<String, dynamic> toJson({
    bool forConfirm = false,
    bool withInstallments = false,
  }) => {
    'merchant_display': merchant.trim(),
    'date': dateToApi(date),
    'time': time == null ? null : timeToApi(time!),
    'total_minor': totalMinor,
    'category_key': category.key,
    'channel': channel.key,
    'note': (note == null || note!.trim().isEmpty) ? null : note!.trim(),
    if (forConfirm) ...{
      'items': [for (final line in lines) line.toJson()],
      'remember_category_for_merchant': rememberCategory,
    },
    if (forConfirm || withInstallments) 'installment_count': installmentCount,
  };
}

/// P12: one refund of a purchase.
class RefundEntry {
  const RefundEntry({required this.id, required this.date, required this.amountMinor});

  final String id;
  final DateTime date;
  final int amountMinor;

  factory RefundEntry.fromJson(Map<String, dynamic> json) => RefundEntry(
    id: json['id'] as String,
    date: _day(json['date'] as String),
    amountMinor: json['amount_minor'] as int,
  );
}

/// P12: a product made from a purchase (its id, name and status).
class ProductBrief {
  const ProductBrief({required this.id, required this.name, required this.status});

  final String id;
  final String name;
  final ProductStatus status;

  factory ProductBrief.fromJson(Map<String, dynamic> json) => ProductBrief(
    id: json['id'] as String,
    name: json['name'] as String,
    status: ProductStatus.fromKey(json['status'] as String?),
  );
}
