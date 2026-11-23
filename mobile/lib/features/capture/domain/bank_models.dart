import '../../installments/domain/installment_models.dart';
import '../../matching/domain/match_models.dart';
import '../../transactions/domain/spending_category.dart';

/// The banks with bank-specific help on the server (DECISIONS D-013). Every other bank (QNB,
/// Ziraat, ...) is read with the general prompt: there is no key for it, the hint stays empty.
enum BankKey {
  garanti('garanti', 'Garanti BBVA'),
  kuveyt('kuveyt', 'Kuveyt Türk'),
  akbank('akbank', 'Akbank');

  const BankKey(this.wireName, this.label);

  final String wireName;
  final String label;
}

/// What kind of row it is: a purchase, or a credit that may be a refund (refunds are P12).
enum BankRowKind { purchase, refund }

/// One row of a bank screenshot after the server read and checked it.
class BankRow {
  const BankRow({
    required this.observationId,
    required this.merchant,
    required this.amountMinor,
    required this.isCredit,
    required this.kind,
    required this.date,
    required this.installmentSeq,
    required this.installmentCount,
    required this.isPending,
    required this.isDuplicate,
    required this.confidence,
    required this.category,
    this.match,
    this.installment,
  });

  final String observationId;
  final String merchant;
  final int amountMinor;
  final bool isCredit;
  final BankRowKind kind;
  final DateTime? date;
  final int? installmentSeq;
  final int? installmentCount;

  /// "Provizyon" / "Bekleyen": not booked yet.
  final bool isPending;

  /// The same row was imported before (the screenshot overlaps an earlier one).
  final bool isDuplicate;

  /// HIGH / MEDIUM / LOW per field (merchant, amount, date, installment).
  final Map<String, String> confidence;
  final SpendingCategory category;

  /// P09: this row is (auto) or may be (suggest) the same purchase as one already saved.
  final BankRowMatch? match;

  /// P10: what an installment row will become (a payment of a plan, an estimated purchase ...).
  final InstallmentPreview? installment;

  /// A purchase that can be saved now.
  bool get isSelectable => kind == BankRowKind.purchase && !isDuplicate;

  /// "KONTROL ET": the app is not sure about the merchant or the date.
  bool get needsCheck =>
      confidence['merchant'] != 'HIGH' || confidence['date'] == 'LOW';

  /// "2/6", "3 taksit", or null.
  String? get installmentLabel {
    final count = installmentCount;
    if (count == null) return null;
    final seq = installmentSeq;
    return seq == null ? '$count taksit' : '$seq/$count';
  }

  factory BankRow.fromJson(Map<String, dynamic> json) {
    final suggestions = json['suggestions'] as Map<String, dynamic>?;
    final categoryKey =
        (suggestions?['category'] as Map<String, dynamic>?)?['key'] as String?;
    final dateText = json['date'] as String?;
    return BankRow(
      observationId: json['observation_id'] as String,
      merchant: json['merchant_raw'] as String,
      amountMinor: json['amount_minor'] as int,
      isCredit: json['direction'] == 'CREDIT',
      kind: json['kind'] == 'REFUND'
          ? BankRowKind.refund
          : BankRowKind.purchase,
      date: dateText == null ? null : DateTime.parse(dateText),
      installmentSeq: json['installment_seq'] as int?,
      installmentCount: json['installment_count'] as int?,
      isPending: json['is_pending'] as bool? ?? false,
      isDuplicate: json['status'] == 'DUPLICATE',
      confidence: {
        for (final entry
            in (json['confidence'] as Map<String, dynamic>? ?? {}).entries)
          entry.key: entry.value as String,
      },
      category: SpendingCategory.fromKey(categoryKey) ?? SpendingCategory.other,
      match: json['match'] == null
          ? null
          : BankRowMatch.fromJson(json['match'] as Map<String, dynamic>),
      installment: json['installment'] == null
          ? null
          : InstallmentPreview.fromJson(
              json['installment'] as Map<String, dynamic>,
            ),
    );
  }
}

/// A row that was found but not imported, with the reason code of the server.
class SkippedRow {
  const SkippedRow({
    required this.merchant,
    required this.amountMinor,
    required this.reason,
  });

  final String merchant;
  final int? amountMinor;
  final String reason;

  /// Turkish text for the reason.
  String get reasonLabel => switch (reason) {
    'PAYMENT' => 'Kart ödemesi',
    'NON_TL_AMOUNT' => 'Puan / TL olmayan tutar',
    'ZERO_AMOUNT' => 'Tutarı yok (0,00)',
    'HEADER_OR_TOTAL' => 'Toplam / başlık satırı',
    _ => 'Okunamadı',
  };

  factory SkippedRow.fromJson(Map<String, dynamic> json) => SkippedRow(
    merchant: json['merchant_raw'] as String,
    amountMinor: json['amount_minor'] as int?,
    reason: json['reason'] as String,
  );
}

/// The answer of `POST /extract/bank-screenshot`.
class BankImport {
  const BankImport({
    required this.bankKey,
    required this.rows,
    required this.skipped,
  });

  final BankKey? bankKey;
  final List<BankRow> rows;
  final List<SkippedRow> skipped;

  factory BankImport.fromJson(Map<String, dynamic> json) {
    final key = json['bank_key'] as String?;
    return BankImport(
      bankKey: BankKey.values.where((b) => b.wireName == key).firstOrNull,
      rows: [
        for (final row in json['rows'] as List<dynamic>)
          BankRow.fromJson(row as Map<String, dynamic>),
      ],
      skipped: [
        for (final row in json['skipped'] as List<dynamic>)
          SkippedRow.fromJson(row as Map<String, dynamic>),
      ],
    );
  }
}

/// What the user changed on one row before saving.
class BankRowEdit {
  const BankRowEdit({
    this.merchant,
    this.date,
    this.amountMinor,
    this.category,
  });

  final String? merchant;
  final DateTime? date;
  final int? amountMinor;
  final SpendingCategory? category;

  BankRowEdit copyWith({
    String? merchant,
    DateTime? date,
    int? amountMinor,
    SpendingCategory? category,
  }) => BankRowEdit(
    merchant: merchant ?? this.merchant,
    date: date ?? this.date,
    amountMinor: amountMinor ?? this.amountMinor,
    category: category ?? this.category,
  );
}

/// The answer of `POST /observations/confirm-batch`.
class BatchResult {
  const BatchResult({
    required this.created,
    required this.skipped,
    this.merged = const [],
    this.suggested = const [],
    this.linked = const [],
  });

  final int created;

  /// observation id -> reason (POSSIBLE_REFUND, NOT_PENDING, MISSING_DATE, ...).
  final Map<String, String> skipped;

  /// Rows that were attached to a purchase you already had (each can be undone).
  final List<UndoableMerge> merged;

  /// Rows that may be the same as an existing purchase: they wait for the user's answer.
  final List<MatchSuggestion> suggested;

  /// P10: installment rows (`k/n`) that became payments of a plan (no spending added).
  final List<LinkedRow> linked;

  factory BatchResult.fromJson(Map<String, dynamic> json) => BatchResult(
    created: (json['created'] as List<dynamic>).length,
    skipped: {
      for (final item in json['skipped'] as List<dynamic>)
        (item as Map<String, dynamic>)['observation_id'] as String:
            item['reason'] as String,
    },
    merged: [
      for (final item in json['merged'] as List<dynamic>? ?? const [])
        UndoableMerge(
          transactionId:
              ((item as Map<String, dynamic>)['transaction']
                      as Map<String, dynamic>)['id']
                  as String,
          observationId: item['observation_id'] as String,
        ),
    ],
    suggested: [
      for (final item in json['suggested'] as List<dynamic>? ?? const [])
        MatchSuggestion.fromJson(item as Map<String, dynamic>),
    ],
    linked: [
      for (final item in json['linked'] as List<dynamic>? ?? const [])
        LinkedRow(
          observationId:
              (item as Map<String, dynamic>)['observation_id'] as String,
          seq: item['seq'] as int,
          count: item['count'] as int,
          transactionId:
              (item['transaction'] as Map<String, dynamic>)['id'] as String,
        ),
    ],
  );
}
