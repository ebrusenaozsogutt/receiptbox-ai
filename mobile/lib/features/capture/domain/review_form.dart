import 'package:material_ui/material_ui.dart' show TimeOfDay;

import '../../transactions/domain/purchase_models.dart';
import '../../transactions/domain/spending_category.dart';
import 'capture_payload.dart';
import 'extraction_result.dart';

/// The fields of the review screen that can carry a "KONTROL ET" flag.
enum ReviewField { merchant, date, time, total, category }

/// One receipt line while the user looks at it or edits it.
class EditableLine {
  const EditableLine({required this.name, this.totalMinor});

  final String name;
  final int? totalMinor;

  EditableLine copyWith({String? name, int? Function()? totalMinor}) =>
      EditableLine(
        name: name ?? this.name,
        totalMinor: totalMinor != null ? totalMinor() : this.totalMinor,
      );
}

/// The line under the items card: do the lines add up to the receipt total?
enum SumCheck {
  /// No lines or no total: nothing to say.
  none,
  matches,
  differs,

  /// A line has no amount, so the sum cannot be checked.
  incomplete,
}

/// Same tolerance as the backend (spec 5.3): 0,05 TL or 1% of the total, whichever is larger.
SumCheck itemsSumCheck(List<EditableLine> lines, int? totalMinor) {
  if (lines.isEmpty || totalMinor == null || totalMinor <= 0) {
    return SumCheck.none;
  }
  if (lines.any((line) => line.totalMinor == null)) return SumCheck.incomplete;
  final sum = lines.fold<int>(0, (total, line) => total + line.totalMinor!);
  final tolerance = [5, (totalMinor / 100).round()].reduce((a, b) => a > b ? a : b);
  return (sum - totalMinor).abs() <= tolerance
      ? SumCheck.matches
      : SumCheck.differs;
}

/// What the review screen shows and edits. Immutable: every edit makes a new one.
class ReviewForm {
  const ReviewForm({
    required this.merchant,
    required this.date,
    required this.time,
    required this.totalMinor,
    required this.category,
    required this.channel,
    required this.note,
    required this.lines,
    required this.flagged,
    required this.linesFlagged,
    required this.suggestedCategory,
  });

  final String merchant;
  final DateTime date;
  final TimeOfDay? time;
  final int? totalMinor;
  final SpendingCategory category;
  final PurchaseChannel channel;
  final String note;
  final List<EditableLine> lines;

  /// Fields the app is not sure about. Editing a field removes it from here.
  final Set<ReviewField> flagged;
  final bool linesFlagged;

  /// What the app suggested, to notice when the user changes the category.
  final SpendingCategory suggestedCategory;

  /// How many things wait for the user: the banner counts them.
  int get pendingChecks => flagged.length + (linesFlagged ? 1 : 0);

  bool get canSave =>
      merchant.trim().isNotEmpty && totalMinor != null && totalMinor! > 0;

  ReviewForm copyWith({
    String? merchant,
    DateTime? date,
    TimeOfDay? Function()? time,
    int? Function()? totalMinor,
    SpendingCategory? category,
    PurchaseChannel? channel,
    String? note,
    List<EditableLine>? lines,
    Set<ReviewField>? flagged,
    bool? linesFlagged,
  }) => ReviewForm(
    merchant: merchant ?? this.merchant,
    date: date ?? this.date,
    time: time != null ? time() : this.time,
    totalMinor: totalMinor != null ? totalMinor() : this.totalMinor,
    category: category ?? this.category,
    channel: channel ?? this.channel,
    note: note ?? this.note,
    lines: lines ?? this.lines,
    flagged: flagged ?? this.flagged,
    linesFlagged: linesFlagged ?? this.linesFlagged,
    suggestedCategory: suggestedCategory,
  );

  /// From what the server read. Everything that is not HIGH is flagged (spec 5.4), except an
  /// absent time, which is simply left empty.
  factory ReviewForm.fromExtraction(
    ExtractionResult result,
    CapturePayload payload,
  ) {
    bool unsure(String field) => result.confidence[field] != 'HIGH';

    final knownMerchant = const {
      'USER_ALIAS',
      'GLOBAL_ALIAS',
      'FUZZY',
    }.contains(result.merchantMatch);
    final merchant = knownMerchant && result.merchantName != null
        ? result.merchantName!
        : (result.merchant ?? '');
    final date = result.date == null
        ? payload.captureDate
        : DateTime.parse(result.date!);
    final time = _parseTime(result.time);
    final category =
        SpendingCategory.fromKey(result.categoryKey) ?? SpendingCategory.other;
    final categorySure =
        result.categorySource == 'USER_RULE' ||
        result.categorySource == 'MERCHANT_DEFAULT';

    return ReviewForm(
      merchant: merchant,
      date: DateTime(date.year, date.month, date.day),
      time: time,
      totalMinor: result.totalMinor,
      category: category,
      channel: payload.qrPayload != null
          ? PurchaseChannel.online
          : PurchaseChannel.inStore,
      note: '',
      lines: [
        for (final line in result.lines)
          EditableLine(name: line.name, totalMinor: line.totalMinor),
      ],
      flagged: {
        if (merchant.trim().isEmpty || unsure('merchant')) ReviewField.merchant,
        if (result.date == null || unsure('date')) ReviewField.date,
        if (time != null && unsure('time')) ReviewField.time,
        if (result.totalMinor == null || unsure('total')) ReviewField.total,
        if (!categorySure) ReviewField.category,
      },
      linesFlagged: result.lines.isNotEmpty && unsure('items'),
      suggestedCategory: category,
    );
  }

  /// When nothing could be read: an empty form, every field to be filled in by the user.
  factory ReviewForm.empty(CapturePayload payload) => ReviewForm(
    merchant: '',
    date: DateTime(
      payload.captureDate.year,
      payload.captureDate.month,
      payload.captureDate.day,
    ),
    time: null,
    totalMinor: null,
    category: SpendingCategory.other,
    channel: payload.qrPayload != null
        ? PurchaseChannel.online
        : PurchaseChannel.inStore,
    note: '',
    lines: const [],
    flagged: const {
      ReviewField.merchant,
      ReviewField.date,
      ReviewField.total,
      ReviewField.category,
    },
    linesFlagged: false,
    suggestedCategory: SpendingCategory.other,
  );

  /// A blank form for a purchase typed in by hand: nothing is flagged, the user fills it in.
  factory ReviewForm.blank(DateTime today) => ReviewForm(
    merchant: '',
    date: DateTime(today.year, today.month, today.day),
    time: null,
    totalMinor: null,
    category: SpendingCategory.other,
    channel: PurchaseChannel.inStore,
    note: '',
    lines: const [],
    flagged: const {},
    linesFlagged: false,
    suggestedCategory: SpendingCategory.other,
  );

  /// To edit a saved purchase.
  factory ReviewForm.fromPurchase(Purchase purchase) => ReviewForm(
    merchant: purchase.merchant,
    date: purchase.date,
    time: purchase.time,
    totalMinor: purchase.totalMinor,
    category: purchase.category ?? SpendingCategory.other,
    channel: purchase.channel,
    note: purchase.note ?? '',
    lines: const [],
    flagged: const {},
    linesFlagged: false,
    suggestedCategory: purchase.category ?? SpendingCategory.other,
  );

  static TimeOfDay? _parseTime(String? text) {
    if (text == null) return null;
    final parts = text.split(':');
    if (parts.length < 2) return null;
    return TimeOfDay(hour: int.parse(parts[0]), minute: int.parse(parts[1]));
  }
}
