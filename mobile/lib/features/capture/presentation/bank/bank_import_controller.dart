import 'dart:async';

import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../../core/networking/api_error.dart';
import '../../../../core/storage/settings_store.dart';
import '../../../transactions/data/transactions_api.dart';
import '../../data/capture_providers.dart';
import '../../data/extraction_api.dart';
import '../../../matching/domain/match_models.dart';
import '../../domain/bank_detector.dart';
import '../../domain/bank_models.dart';
import '../../domain/capture_payload.dart';

part 'bank_import_controller.g.dart';

enum BankPhase { idle, extracting, ready, saving, failed }

class BankImportState {
  const BankImportState({
    this.phase = BankPhase.idle,
    this.bank,
    this.rows = const [],
    this.skipped = const [],
    this.selected = const {},
    this.edits = const {},
    this.errorCode,
    this.errorMessage,
    this.result,
  });

  final BankPhase phase;

  /// The bank the server was told about (null: unknown, read with the general prompt).
  final BankKey? bank;
  final List<BankRow> rows;
  final List<SkippedRow> skipped;

  /// observation ids of the rows that will be saved.
  final Set<String> selected;
  final Map<String, BankRowEdit> edits;
  final String? errorCode;
  final String? errorMessage;

  /// The capture outcome, only for the debug link to "Okunan bilgiler".
  final CaptureResult? result;

  List<BankRow> get purchases => rows
      .where((r) => r.kind == BankRowKind.purchase && !r.isDuplicate)
      .toList();
  List<BankRow> get possibleRefunds => rows
      .where((r) => r.kind == BankRowKind.refund && !r.isDuplicate)
      .toList();
  List<BankRow> get duplicates => rows.where((r) => r.isDuplicate).toList();

  BankImportState copyWith({
    BankPhase? phase,
    BankKey? Function()? bank,
    List<BankRow>? rows,
    List<SkippedRow>? skipped,
    Set<String>? selected,
    Map<String, BankRowEdit>? edits,
    String? Function()? errorCode,
    String? Function()? errorMessage,
  }) => BankImportState(
    phase: phase ?? this.phase,
    bank: bank != null ? bank() : this.bank,
    rows: rows ?? this.rows,
    skipped: skipped ?? this.skipped,
    selected: selected ?? this.selected,
    edits: edits ?? this.edits,
    errorCode: errorCode != null ? errorCode() : this.errorCode,
    errorMessage: errorMessage != null ? errorMessage() : this.errorMessage,
    result: result,
  );
}

/// What saving gave back. P09: [merged] rows were attached to purchases you already had (each can
/// be undone); [suggested] rows wait for the user's answer and are not purchases yet.
class BankSaveOutcome {
  const BankSaveOutcome({
    required this.created,
    required this.skipped,
    this.merged = const [],
    this.suggested = const [],
    this.linked = 0,
  });

  final int created;
  final int skipped;

  /// P10: installment rows that became payments of a purchase (no spending was added).
  final int linked;
  final List<UndoableMerge> merged;
  final List<MatchSuggestion> suggested;
}

/// The state and the actions behind the bank import review screen (P08). Only the masked text of
/// the screenshot goes to the server; the image is never kept or uploaded.
@riverpod
class BankImportController extends _$BankImportController {
  CapturePayload? _payload;

  @override
  BankImportState build() => const BankImportState();

  /// Read the rows with the bank the phone guessed from the masked text.
  Future<void> start(CaptureResult result) async {
    _payload = result.payload;
    final guess = const BankDetector().detect(result.payload.maskedText);
    state = BankImportState(
      phase: BankPhase.extracting,
      bank: guess,
      result: result,
    );
    await _extract(guess);
  }

  Future<void> _extract(BankKey? bank) async {
    final payload = _payload;
    if (payload == null) return;
    state = state.copyWith(
      phase: BankPhase.extracting,
      bank: () => bank,
      errorCode: () => null,
      errorMessage: () => null,
    );
    try {
      final imported = await ref
          .read(extractionApiProvider)
          .extractBank(
            payload,
            bankHint: bank?.wireName,
            aiConsent: ref.read(aiConsentProvider),
          );
      if (!ref.mounted) return;
      state = state.copyWith(
        phase: BankPhase.ready,
        rows: imported.rows,
        skipped: imported.skipped,
        selected: {
          for (final row in imported.rows)
            if (row.isSelectable) row.observationId,
        },
        edits: const {},
      );
    } on AiConsentOffException catch (error) {
      _fail('AI_CONSENT_OFF', error.message);
    } on ApiError catch (error) {
      _fail(error.code, error.message);
    }
  }

  void _fail(String code, String message) {
    if (!ref.mounted) return;
    state = state.copyWith(
      phase: BankPhase.failed,
      errorCode: () => code,
      errorMessage: () => message,
    );
  }

  Future<void> retry() => _extract(state.bank);

  /// "Banka: ▾": the earlier rows are dropped on the server and the screenshot text is read again
  /// with the other bank's help.
  Future<void> changeBank(BankKey? bank) async {
    if (bank == state.bank && state.phase == BankPhase.ready) return;
    await _rejectAll();
    await _extract(bank);
  }

  void toggle(String id) {
    final selected = {...state.selected};
    if (!selected.remove(id)) selected.add(id);
    state = state.copyWith(selected: selected);
  }

  void selectAll(bool value) {
    state = state.copyWith(
      selected: value
          ? {
              for (final row in state.rows)
                if (row.isSelectable) row.observationId,
            }
          : <String>{},
    );
  }

  void edit(String id, BankRowEdit edit) {
    state = state.copyWith(edits: {...state.edits, id: edit});
  }

  /// "Seçilenleri Kaydet". The rows the user did not select are discarded on the server; credit
  /// rows stay as possible refunds (P12).
  Future<BankSaveOutcome> save() async {
    final ids = [
      for (final row in state.rows)
        if (state.selected.contains(row.observationId) && row.isSelectable)
          row.observationId,
    ];
    if (ids.isEmpty) throw StateError('nothing is selected');
    state = state.copyWith(phase: BankPhase.saving);
    try {
      final api = ref.read(transactionsApiProvider);
      final result = await api.confirmBatch(ids, state.edits);
      // What the user left out is discarded (best effort).
      for (final row in state.purchases) {
        if (!ids.contains(row.observationId)) {
          await _rejectQuietly(row.observationId);
        }
      }
      return BankSaveOutcome(
        created: result.created,
        skipped: result.skipped.length,
        merged: result.merged,
        suggested: result.suggested,
        linked: result.linked.length,
      );
    } on Object {
      if (ref.mounted) state = state.copyWith(phase: BankPhase.ready);
      rethrow;
    }
  }

  /// "Vazgeç": every row of this screenshot is discarded on the server.
  Future<void> discard() => _rejectAll();

  Future<void> _rejectAll() async {
    for (final row in state.rows) {
      if (!row.isDuplicate) await _rejectQuietly(row.observationId);
    }
  }

  Future<void> _rejectQuietly(String id) async {
    try {
      await ref.read(transactionsApiProvider).reject(id);
    } on ApiError {
      // It stays pending on the server; nothing is lost and it can be rejected later.
    }
  }
}
