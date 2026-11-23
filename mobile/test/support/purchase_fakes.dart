import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:receiptbox/core/networking/api_error.dart';
import 'package:receiptbox/features/capture/domain/bank_models.dart';
import 'package:receiptbox/features/installments/domain/installment_models.dart';
import 'package:receiptbox/features/matching/domain/match_models.dart';
import 'package:receiptbox/features/transactions/data/transactions_api.dart';
import 'package:receiptbox/features/transactions/domain/purchase_models.dart';
import 'package:receiptbox/features/transactions/domain/spending_category.dart';

ApiError fakeApiError(String code, {int? status}) =>
    ApiError(code: code, message: messageForCode(code), statusCode: status);

/// 1x1 transparent PNG: something `Image.memory` can really decode.
final Uint8List tinyPng = Uint8List.fromList(const [
  0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D, //
  0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
  0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
  0x0D, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0xF8, 0xFF, 0xFF, 0x3F,
  0x00, 0x05, 0xFE, 0x02, 0xFE, 0xA7, 0x35, 0x81, 0x84, 0x00, 0x00, 0x00,
  0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
]);

/// The purchases endpoints in memory. Tests fill [purchases] and read back what the app sent.
class FakeTransactionsApi implements TransactionsApi {
  final List<PurchaseDetail> purchases = [];
  final confirmed = <({String observationId, PurchaseInput input})>[];
  final created = <PurchaseInput>[];
  final updated = <({String id, PurchaseInput input})>[];
  final deleted = <String>[];
  final rejected = <String>[];
  final listCalls =
      <({SpendingCategory? category, String? search, int offset})>[];

  /// Thrown by the next write (confirm / createManual / update / delete), then cleared.
  ApiError? writeError;

  /// Thrown by reject() while set.
  ApiError? rejectError;
  Completer<void>? confirmGate;
  int _counter = 0;

  PurchaseDetail add({
    String? id,
    String merchant = 'Migros',
    SpendingCategory? category = SpendingCategory.grocery,
    DateTime? date,
    int totalMinor = 27030,
    List<EvidenceKind> evidence = const [EvidenceKind.receipt],
    List<ReceiptLine> lines = const [],
    List<DocumentInfo> documents = const [],
    String? note,
    List<EvidenceItem> evidenceItems = const [],
    InstallmentPlan? plan,
    bool isEstimated = false,
  }) {
    final detail = PurchaseDetail(
      purchase: Purchase(
        id: id ?? 'tx-${++_counter}',
        merchant: merchant,
        category: category,
        date: date ?? DateTime(2026, 11, 14),
        time: null,
        totalMinor: totalMinor,
        channel: PurchaseChannel.inStore,
        note: note,
        documentCount: documents.length,
        isEstimated: isEstimated,
        isInstallment: plan != null,
      ),
      evidence: evidence,
      lines: lines,
      documents: documents,
      evidenceItems: evidenceItems,
      plan: plan,
    );
    purchases.add(detail);
    return detail;
  }

  PurchaseDetail _from(String id, PurchaseInput input, EvidenceKind evidence) =>
      PurchaseDetail(
        purchase: Purchase(
          id: id,
          merchant: input.merchant,
          category: input.category,
          date: input.date,
          time: input.time,
          totalMinor: input.totalMinor,
          channel: input.channel,
          note: input.note,
          documentCount: 0,
        ),
        evidence: [evidence],
        lines: [
          for (final line in input.lines)
            ReceiptLine(
              name: line.name,
              quantity: '1',
              totalMinor: line.totalMinor,
            ),
        ],
        documents: const [],
      );

  void _checkWrite() {
    final error = writeError;
    if (error != null) {
      writeError = null;
      throw error;
    }
  }

  @override
  Future<PurchasePage> list({
    DateTime? from,
    DateTime? to,
    SpendingCategory? category,
    String? search,
    int limit = 30,
    int offset = 0,
  }) async {
    listCalls.add((category: category, search: search, offset: offset));
    final needle = search?.trim().toLowerCase() ?? '';
    final matching = [
      for (final p in purchases)
        if ((from == null || !p.purchase.date.isBefore(from)) &&
            (to == null || !p.purchase.date.isAfter(to)) &&
            (category == null || p.purchase.category == category) &&
            (needle.isEmpty ||
                p.purchase.merchant.toLowerCase().contains(needle)))
          p.purchase,
    ]..sort((a, b) => b.date.compareTo(a.date));
    return PurchasePage(
      items: matching.skip(offset).take(limit).toList(),
      count: matching.length,
      sumMinor: matching.fold(0, (sum, p) => sum + p.totalMinor),
    );
  }

  @override
  Future<PurchaseDetail> detail(String id) async {
    final found = purchases.where((p) => p.purchase.id == id);
    if (found.isEmpty) throw fakeApiError('NOT_FOUND', status: 404);
    return found.first;
  }

  /// P09: the answer of the next confirm / createManual instead of a new purchase (a merge,
  /// or a question). Cleared after use.
  SaveResult? nextSave;

  @override
  Future<SaveResult> createManual(PurchaseInput input) async {
    _checkWrite();
    created.add(input);
    final scripted = nextSave;
    if (scripted != null) {
      nextSave = null;
      return scripted;
    }
    final detail = _from('tx-${++_counter}', input, EvidenceKind.manual);
    purchases.add(detail);
    return Saved(detail);
  }

  @override
  Future<PurchaseDetail> update(String id, PurchaseInput input) async {
    _checkWrite();
    updated.add((id: id, input: input));
    final old = await detail(id);
    final next = _from(id, input, old.evidence.first);
    final replaced = PurchaseDetail(
      purchase: next.purchase,
      evidence: old.evidence,
      lines: old.lines,
      documents: old.documents,
    );
    purchases[purchases.indexOf(old)] = replaced;
    return replaced;
  }

  @override
  Future<void> delete(String id) async {
    _checkWrite();
    deleted.add(id);
    purchases.removeWhere((p) => p.purchase.id == id);
  }

  @override
  Future<SaveResult> confirm(String observationId, PurchaseInput input) async {
    if (confirmGate != null) await confirmGate!.future;
    _checkWrite();
    confirmed.add((observationId: observationId, input: input));
    final scripted = nextSave;
    if (scripted != null) {
      nextSave = null;
      return scripted;
    }
    final detail = _from('tx-${++_counter}', input, EvidenceKind.receipt);
    purchases.add(detail);
    return Saved(detail);
  }

  final batches = <({List<String> ids, Map<String, BankRowEdit> edits})>[];
  BatchResult batchResult = const BatchResult(created: 0, skipped: {});
  Completer<void>? batchGate;

  @override
  Future<BatchResult> confirmBatch(
    List<String> ids,
    Map<String, BankRowEdit> edits,
  ) async {
    if (batchGate != null) await batchGate!.future;
    _checkWrite();
    batches.add((ids: ids, edits: edits));
    return BatchResult(
      created:
          ids.length -
          batchResult.skipped.length -
          batchResult.merged.length -
          batchResult.linked.length -
          batchResult.suggested.length,
      skipped: batchResult.skipped,
      merged: batchResult.merged,
      suggested: batchResult.suggested,
      linked: batchResult.linked,
    );
  }

  // ---- matching (P09) -----------------------------------------------------------------------

  /// What `GET /matches` answers.
  List<MatchSuggestion> pending = [];
  final accepted = <String>[];
  final rejectedMatches = <String>[];
  final unmerged = <({String transactionId, String observationId})>[];

  /// The purchase the next accept / reject answers with.
  PurchaseDetail? matchAnswer;
  ApiError? matchError;

  @override
  Future<List<MatchSuggestion>> pendingMatches() async => [...pending];

  PurchaseDetail _answer() => matchAnswer ?? add(merchant: 'Cevaplanan');

  @override
  Future<PurchaseDetail> acceptMatch(String decisionId) async {
    final error = matchError;
    if (error != null) throw error;
    accepted.add(decisionId);
    pending = [
      for (final m in pending)
        if (m.id != decisionId) m,
    ];
    return _answer();
  }

  @override
  Future<PurchaseDetail> rejectMatch(String decisionId) async {
    final error = matchError;
    if (error != null) throw error;
    rejectedMatches.add(decisionId);
    pending = [
      for (final m in pending)
        if (m.id != decisionId) m,
    ];
    return _answer();
  }

  @override
  Future<UnmergeResult> unmerge(
    String transactionId,
    String observationId,
  ) async {
    final error = matchError;
    if (error != null) throw error;
    unmerged.add((transactionId: transactionId, observationId: observationId));
    final kept = await detail(transactionId);
    return UnmergeResult(
      transaction: kept,
      newTransaction: add(merchant: 'Ayrılan'),
    );
  }

  // ---- installments (P10) -------------------------------------------------------------------

  final plansPut = <({String transactionId, int count})>[];
  final plansCancelled = <({String planId, bool cancel})>[];

  /// What `GET /installments/schedule` answers.
  InstallmentSchedule scheduleAnswer = const InstallmentSchedule(
    months: [],
    remainingMinor: 0,
  );
  ApiError? planError;

  @override
  Future<PurchaseDetail> putPlan(
    String transactionId, {
    required int count,
    DateTime? firstDueMonth,
    int? totalPayableMinor,
  }) async {
    final error = planError;
    if (error != null) throw error;
    plansPut.add((transactionId: transactionId, count: count));
    return detail(transactionId);
  }

  @override
  Future<PurchaseDetail> setPlanCancelled(
    String planId, {
    required bool cancel,
  }) async {
    final error = planError;
    if (error != null) throw error;
    plansCancelled.add((planId: planId, cancel: cancel));
    return purchases.first;
  }

  @override
  Future<InstallmentSchedule> schedule({DateTime? from, DateTime? to}) async =>
      scheduleAnswer;

  @override
  Future<void> reject(String observationId) async {
    final error = rejectError;
    if (error != null) throw error;
    rejected.add(observationId);
  }
}

/// The documents endpoints in memory.
class FakeDocumentsApi implements DocumentsApi {
  final uploads = <({String mimeType, String type, String transactionId})>[];

  /// How many of the next uploads fail before one works.
  int failUploads = 0;
  final Map<String, Uint8List> files = {};

  @override
  Future<DocumentInfo> upload(
    File file, {
    required String mimeType,
    required String type,
    required String transactionId,
  }) async {
    if (failUploads > 0) {
      failUploads--;
      throw fakeApiError('NETWORK_UNREACHABLE');
    }
    uploads.add((mimeType: mimeType, type: type, transactionId: transactionId));
    return DocumentInfo(
      id: 'doc-${uploads.length}',
      type: type,
      mimeType: mimeType,
    );
  }

  @override
  Future<String> contentUrl(String documentId) async =>
      'http://fake.test/documents/$documentId/content?token=t';

  @override
  Future<Uint8List> content(String documentId) async =>
      files[documentId] ?? tinyPng;
}
