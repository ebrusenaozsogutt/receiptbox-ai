import 'dart:async';
import 'dart:io';

import 'package:material_ui/material_ui.dart' show TimeOfDay;
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../../core/networking/api_error.dart';
import '../../../../core/ocr/file_cleanup.dart';
import '../../../../core/storage/settings_store.dart';
import '../../../transactions/data/transactions_api.dart';
import '../../../transactions/domain/purchase_models.dart';
import '../../../transactions/domain/spending_category.dart';
import '../../../matching/domain/match_models.dart';
import '../../data/capture_providers.dart';
import '../../data/extraction_api.dart';
import '../../domain/capture_payload.dart';
import '../../domain/review_form.dart';

part 'review_controller.g.dart';

enum ReviewPhase { idle, extracting, editing, saving }

class ReviewState {
  const ReviewState({
    this.phase = ReviewPhase.idle,
    this.form,
    this.observationId,
    this.notice,
    this.payload,
    this.retainedImage,
    this.result,
  });

  final ReviewPhase phase;
  final ReviewForm? form;

  /// The pending observation on the server. Null when nothing could be read: the purchase is
  /// then saved as a manual entry.
  final String? observationId;

  /// Why the form is empty (extraction failed, AI reading off ...), in Turkish.
  final String? notice;
  final CapturePayload? payload;
  final File? retainedImage;

  /// The whole capture outcome, only for the debug link to "Okunan bilgiler".
  final CaptureResult? result;

  bool get isManual => observationId == null;
  bool get retainedIsPdf => retainedImage?.path.endsWith('.pdf') ?? false;

  ReviewState copyWith({ReviewPhase? phase, ReviewForm? form}) => ReviewState(
    phase: phase ?? this.phase,
    form: form ?? this.form,
    observationId: observationId,
    notice: notice,
    payload: payload,
    retainedImage: retainedImage,
    result: result,
  );
}

/// What saving gave back. [imageUploaded] is null when there was no image to upload.
///
/// P09: when the record may be a purchase you already have, nothing was created: [detail] is null
/// and [suggestions] holds the question. The kept image waits for the answer
/// ([ReviewController.attachImageAfterAnswer]).
class SaveOutcome {
  const SaveOutcome({
    this.detail,
    this.suggestions = const [],
    required this.imageUploaded,
  });

  final PurchaseDetail? detail;
  final List<MatchSuggestion> suggestions;
  final bool? imageUploaded;

  bool get needsAnswer => detail == null;
}

/// The state and the actions behind the receipt review screen (Figma "02 · Fiş Kontrol").
@riverpod
class ReviewController extends _$ReviewController {
  @override
  ReviewState build() => const ReviewState();

  /// Read the captured receipt on the server and open the form. When that is not possible the
  /// form opens empty with a notice, so the user can still save the purchase by hand.
  Future<void> start(CaptureResult result) async {
    final payload = result.payload;
    state = ReviewState(
      phase: ReviewPhase.extracting,
      payload: payload,
      retainedImage: result.retainedImage,
      result: result,
    );
    try {
      final extraction = await ref
          .read(extractionApiProvider)
          .extract(payload, aiConsent: ref.read(aiConsentProvider));
      if (!ref.mounted) return;
      state = ReviewState(
        phase: ReviewPhase.editing,
        form: ReviewForm.fromExtraction(extraction, payload),
        observationId: extraction.observationId,
        payload: payload,
        retainedImage: result.retainedImage,
        result: result,
      );
    } on AiConsentOffException {
      _manual(
        payload,
        result,
        'Yapay zekâ ile okuma kapalı. Bilgileri kendin girebilirsin.',
      );
    } on ApiError catch (error) {
      _manual(payload, result, _noticeFor(error));
    }
  }

  void _manual(CapturePayload payload, CaptureResult result, String notice) {
    if (!ref.mounted) return;
    state = ReviewState(
      phase: ReviewPhase.editing,
      form: ReviewForm.empty(payload),
      notice: notice,
      payload: payload,
      retainedImage: result.retainedImage,
      result: result,
    );
  }

  static String _noticeFor(ApiError error) => switch (error.code) {
    'EXTRACTION_REJECTED' =>
      'Fiş güvenilir okunamadı. Bilgileri kendin girebilirsin.',
    'QR_INVALID' =>
      'QR kodu okunamadı. Bilgileri kendin girebilirsin.',
    'NETWORK_UNREACHABLE' || 'NETWORK_TIMEOUT' =>
      'Sunucuya ulaşılamadı. Bilgileri kendin girebilirsin.',
    _ => 'Fiş şu an okunamadı. Bilgileri kendin girebilirsin.',
  };

  // ---- edits: every edit also clears that field's "KONTROL ET" flag --------------------------

  void _edit(ReviewForm Function(ReviewForm form) change) {
    final form = state.form;
    if (form == null) return;
    state = state.copyWith(form: change(form));
  }

  Set<ReviewField> _without(ReviewForm form, ReviewField field) => {
    ...form.flagged,
  }..remove(field);

  void setMerchant(String value) => _edit(
    (f) => f.copyWith(
      merchant: value,
      flagged: value.trim().isEmpty
          ? f.flagged
          : _without(f, ReviewField.merchant),
    ),
  );

  void setDate(DateTime value) => _edit(
    (f) => f.copyWith(
      date: DateTime(value.year, value.month, value.day),
      flagged: _without(f, ReviewField.date),
    ),
  );

  void setTime(TimeOfDay? value) => _edit(
    (f) => f.copyWith(time: () => value, flagged: _without(f, ReviewField.time)),
  );

  void setTotal(int? minor) => _edit(
    (f) => f.copyWith(
      totalMinor: () => minor,
      flagged: minor == null ? f.flagged : _without(f, ReviewField.total),
    ),
  );

  void setCategory(SpendingCategory value) => _edit(
    (f) => f.copyWith(
      category: value,
      flagged: _without(f, ReviewField.category),
    ),
  );

  void setChannel(PurchaseChannel value) =>
      _edit((f) => f.copyWith(channel: value));

  void setNote(String value) => _edit((f) => f.copyWith(note: value));

  void setLines(List<EditableLine> lines) =>
      _edit((f) => f.copyWith(lines: lines, linesFlagged: false));

  // ---- leaving ---------------------------------------------------------------------------------

  /// True when the user changed the category the app suggested: the screen then asks "Bu mağaza
  /// için hep böyle olsun mu?". (Only for a receipt that has a pending observation.)
  bool get categoryWasChanged {
    final form = state.form;
    return form != null &&
        !state.isManual &&
        form.category != form.suggestedCategory;
  }

  Future<SaveOutcome> save({required bool rememberCategory}) async {
    final form = state.form;
    if (form == null || !form.canSave) {
      throw StateError('the form is not ready to be saved');
    }
    state = state.copyWith(phase: ReviewPhase.saving);
    try {
      final input = PurchaseInput(
        merchant: form.merchant,
        date: form.date,
        time: form.time,
        totalMinor: form.totalMinor!,
        category: form.category,
        channel: form.channel,
        note: form.note,
        lines: [
          for (final line in form.lines)
            if (line.name.trim().isNotEmpty)
              LineInput(name: line.name.trim(), totalMinor: line.totalMinor),
        ],
        rememberCategory: rememberCategory,
      );
      final api = ref.read(transactionsApiProvider);
      final observationId = state.observationId;
      final result = observationId == null
          ? await api.createManual(input)
          : await api.confirm(observationId, input);

      switch (result) {
        case NeedsAnswer(:final suggestions):
          // Nothing exists yet: the image is kept until the user answers.
          if (ref.mounted) state = state.copyWith(phase: ReviewPhase.editing);
          return SaveOutcome(suggestions: suggestions, imageUploaded: null);
        case Saved(:final detail):
          return SaveOutcome(
            detail: detail,
            imageUploaded: await attachImageAfterAnswer(detail),
          );
      }
    } on Object {
      if (ref.mounted) state = state.copyWith(phase: ReviewPhase.editing);
      rethrow;
    }
  }

  /// Upload the kept image to the purchase (new, or the one the receipt was merged into) and
  /// delete it. Null when there is no image.
  Future<bool?> attachImageAfterAnswer(PurchaseDetail detail) async {
    final image = state.retainedImage;
    final uploaded = image == null
        ? null
        : await _upload(image, detail.purchase.id);
    await deleteQuietly(image);
    return uploaded;
  }

  /// The question was left unanswered: the kept image is not needed any more.
  Future<void> dropImage() => deleteQuietly(state.retainedImage);

  Future<bool> _upload(File image, String transactionId) async {
    final isPdf = image.path.endsWith('.pdf');
    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        await ref
            .read(documentsApiProvider)
            .upload(
              image,
              mimeType: isPdf ? 'application/pdf' : 'image/jpeg',
              type: isPdf ? 'INVOICE' : 'RECEIPT_IMAGE',
              transactionId: transactionId,
            );
        return true;
      } on ApiError {
        // one more try, then the purchase stays without its image
      }
    }
    return false;
  }

  /// "Vazgeç": the pending receipt is rejected on the server and the kept image is deleted.
  Future<void> discard() async {
    final observationId = state.observationId;
    final image = state.retainedImage;
    if (observationId != null) {
      try {
        await ref.read(transactionsApiProvider).reject(observationId);
      } on ApiError {
        // It stays pending on the server; nothing is lost and it can be rejected later.
      }
    }
    await deleteQuietly(image);
  }
}
