import 'package:material_ui/material_ui.dart' show TimeOfDay;

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

class PurchaseDetail {
  const PurchaseDetail({
    required this.purchase,
    required this.evidence,
    required this.lines,
    required this.documents,
  });

  final Purchase purchase;
  final List<EvidenceKind> evidence;
  final List<ReceiptLine> lines;
  final List<DocumentInfo> documents;

  factory PurchaseDetail.fromJson(Map<String, dynamic> json) => PurchaseDetail(
    purchase: Purchase.fromJson(json),
    evidence: [
      for (final e in json['evidence'] as List<dynamic>)
        EvidenceKind.fromSource(
          (e as Map<String, dynamic>)['source'] as String,
        ),
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

  Map<String, dynamic> toJson({bool forConfirm = false}) => {
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
  };
}
