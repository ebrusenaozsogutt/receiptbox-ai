import 'package:material_ui/material_ui.dart' show TimeOfDay;

import '../../transactions/domain/purchase_models.dart';
import '../../transactions/domain/spending_category.dart';

DateTime _day(String iso) {
  final parts = iso.split('-').map(int.parse).toList();
  return DateTime(parts[0], parts[1], parts[2]);
}

TimeOfDay? _time(String? text) {
  if (text == null || text.isEmpty) return null;
  final parts = text.split(':');
  return TimeOfDay(hour: int.parse(parts[0]), minute: int.parse(parts[1]));
}

/// An existing purchase a new record may be the same as (backend `MatchTransactionOut`).
class MatchTransaction {
  const MatchTransaction({
    required this.id,
    required this.merchant,
    required this.category,
    required this.date,
    required this.time,
    required this.totalMinor,
    required this.sources,
  });

  final String id;
  final String merchant;
  final SpendingCategory? category;
  final DateTime date;
  final TimeOfDay? time;
  final int totalMinor;

  /// What is already attached to it (Fiş, Banka, ...).
  final List<EvidenceKind> sources;

  factory MatchTransaction.fromJson(Map<String, dynamic> json) =>
      MatchTransaction(
        id: json['id'] as String,
        merchant: json['merchant_display'] as String,
        category: SpendingCategory.fromKey(json['category_key'] as String?),
        date: _day(json['purchase_date'] as String),
        time: _time(json['purchase_time'] as String?),
        totalMinor: json['total_minor'] as int,
        sources: [
          for (final source in json['sources'] as List<dynamic>)
            EvidenceKind.fromSource(source as String),
        ],
      );
}

/// The new record that waits for the user's answer, as the user reviewed it.
class MatchObservation {
  const MatchObservation({
    required this.id,
    required this.source,
    required this.merchant,
    required this.date,
    required this.time,
    required this.totalMinor,
  });

  final String id;
  final EvidenceKind source;
  final String merchant;
  final DateTime date;
  final TimeOfDay? time;
  final int totalMinor;

  factory MatchObservation.fromJson(Map<String, dynamic> json) =>
      MatchObservation(
        id: json['id'] as String,
        source: EvidenceKind.fromSource(json['source'] as String),
        merchant: json['merchant_display'] as String,
        date: _day(json['purchase_date'] as String),
        time: _time(json['purchase_time'] as String?),
        totalMinor: json['total_minor'] as int,
      );
}

/// "Bu işlem şununla aynı olabilir": one suggestion (backend `MatchOut`). Answer it with
/// accept ("Birleştir") or reject ("Ayrı kalsın").
class MatchSuggestion {
  const MatchSuggestion({
    required this.id,
    required this.score,
    required this.observation,
    required this.transaction,
    this.installmentSeq,
    this.installmentCount,
  });

  /// P10: "this may be payment k of n of that purchase" (a row with a marker that fits several
  /// plans, or a row without one that equals total/n). Null for "the same purchase" (P09).
  final int? installmentSeq;
  final int? installmentCount;

  bool get isInstallment => installmentCount != null;

  /// The decision id.
  final String id;

  /// 0-100.
  final double score;
  final MatchObservation observation;
  final MatchTransaction transaction;

  factory MatchSuggestion.fromJson(Map<String, dynamic> json) =>
      MatchSuggestion(
        id: json['id'] as String,
        score: (json['score'] as num).toDouble(),
        observation: MatchObservation.fromJson(
          json['observation'] as Map<String, dynamic>,
        ),
        transaction: MatchTransaction.fromJson(
          json['transaction'] as Map<String, dynamic>,
        ),
        installmentSeq: json['match_type'] == 'INSTALLMENT'
            ? json['installment_seq'] as int?
            : null,
        installmentCount: json['match_type'] == 'INSTALLMENT'
            ? json['installment_count'] as int?
            : null,
      );
}

/// Suggestions of one waiting record, grouped (one record can have several candidates).
Map<String, List<MatchSuggestion>> groupByObservation(
  List<MatchSuggestion> suggestions,
) {
  final groups = <String, List<MatchSuggestion>>{};
  for (final suggestion in suggestions) {
    groups.putIfAbsent(suggestion.observation.id, () => []).add(suggestion);
  }
  return groups;
}

/// What the bank import review shows on a row (backend `BankRowMatchOut`): the row WILL be
/// merged ([auto]) or the user is asked after saving ([suggest]).
enum BankMatchState { auto, suggest }

class BankRowMatch {
  const BankRowMatch({
    required this.state,
    required this.score,
    required this.transaction,
  });

  final BankMatchState state;
  final double score;
  final MatchTransaction transaction;

  factory BankRowMatch.fromJson(Map<String, dynamic> json) => BankRowMatch(
    state: json['state'] == 'AUTO'
        ? BankMatchState.auto
        : BankMatchState.suggest,
    score: (json['score'] as num).toDouble(),
    transaction: MatchTransaction.fromJson(
      json['transaction'] as Map<String, dynamic>,
    ),
  );
}

/// One merge that can be undone: [observationId] leaves [transactionId] ("Geri al" / "Ayır").
class UndoableMerge {
  const UndoableMerge({
    required this.transactionId,
    required this.observationId,
  });

  final String transactionId;
  final String observationId;
}

/// The two purchases after "Ayır".
class UnmergeResult {
  const UnmergeResult({
    required this.transaction,
    required this.newTransaction,
  });

  final PurchaseDetail transaction;
  final PurchaseDetail newTransaction;

  factory UnmergeResult.fromJson(Map<String, dynamic> json) => UnmergeResult(
    transaction: PurchaseDetail.fromJson(
      json['transaction'] as Map<String, dynamic>,
    ),
    newTransaction: PurchaseDetail.fromJson(
      json['new_transaction'] as Map<String, dynamic>,
    ),
  );
}

/// What saving a purchase (a reviewed receipt, a manual entry) gave back.
sealed class SaveResult {
  const SaveResult();
}

/// The purchase exists: new, or the record was attached to one you had ([PurchaseDetail.merge]).
class Saved extends SaveResult {
  const Saved(this.detail);

  final PurchaseDetail detail;
}

/// It may be a purchase you already have: nothing was created, the user decides first.
class NeedsAnswer extends SaveResult {
  const NeedsAnswer(this.suggestions);

  final List<MatchSuggestion> suggestions;
}
