import '../../../core/utils/money_format.dart';

/// What the backend answered for one capture (`POST /extract/receipt` or `/extract/einvoice-qr`).
/// Only what the debug panel shows; P07 builds the real review screen on top of the same JSON.
class ExtractionResult {
  const ExtractionResult({
    required this.observationId,
    required this.merchant,
    required this.date,
    required this.total,
    required this.itemCount,
    required this.confidence,
    required this.merchantMatch,
    required this.merchantName,
    required this.categoryKey,
    required this.categorySource,
    required this.aiUsed,
    required this.usedQr,
    this.time,
    this.totalMinor,
    this.lines = const [],
    this.installmentCount,
  });

  final String observationId;
  final String? merchant; // as read from the receipt
  final String? date; // yyyy-mm-dd
  final String? total; // "2499.00"
  final int itemCount;

  /// HIGH / MEDIUM / LOW per field (merchant, date, time, total, ...).
  final Map<String, String> confidence;

  /// USER_ALIAS / GLOBAL_ALIAS / FUZZY / NEW / NONE and the name of the matched merchant.
  final String merchantMatch;
  final String? merchantName;
  final String categoryKey;

  /// USER_RULE / MERCHANT_DEFAULT / LLM / FALLBACK.
  final String categorySource;

  /// The AI provider read the text (always true for receipts; for QR only with consent).
  final bool aiUsed;
  final bool usedQr;

  /// "18:42:00", when the receipt has a (credible) time.
  final String? time;

  /// The total in kuruş (the API sends it as text like "270.30").
  final int? totalMinor;

  /// The receipt lines the model found.
  final List<ExtractedLine> lines;
  final int? installmentCount;

  factory ExtractionResult.fromJson(
    Map<String, dynamic> json, {
    required bool usedQr,
  }) {
    final extraction = json['extraction'] as Map<String, dynamic>;
    final suggestions = json['suggestions'] as Map<String, dynamic>;
    final merchant = suggestions['merchant'] as Map<String, dynamic>;
    final category = suggestions['category'] as Map<String, dynamic>;
    return ExtractionResult(
      observationId: json['observation_id'] as String,
      merchant: extraction['merchant_raw'] as String?,
      date: extraction['date'] as String?,
      total: extraction['total'] as String?,
      itemCount: (extraction['items'] as List<dynamic>).length,
      confidence: {
        for (final entry
            in (json['confidence'] as Map<String, dynamic>).entries)
          entry.key: entry.value as String,
      },
      merchantMatch: merchant['match'] as String,
      merchantName: merchant['canonical_name'] as String?,
      categoryKey: category['key'] as String,
      categorySource: category['source'] as String,
      aiUsed: json['ai_used'] as bool? ?? true,
      usedQr: usedQr,
      time: extraction['time'] as String?,
      totalMinor: _minor(extraction['total']),
      lines: [
        for (final item in extraction['items'] as List<dynamic>)
          ExtractedLine(
            name: (item as Map<String, dynamic>)['name_raw'] as String,
            totalMinor: _minor(item['total_price']),
          ),
      ],
      installmentCount: extraction['installment_count'] as int?,
    );
  }

  static int? _minor(Object? decimalText) =>
      decimalText is String ? parseMoneyToMinor(decimalText) : null;
}

/// A receipt line from the extraction (before the user edits it).
class ExtractedLine {
  const ExtractedLine({required this.name, required this.totalMinor});

  final String name;
  final int? totalMinor;
}
