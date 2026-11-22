import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/features/capture/domain/bank_models.dart';
import 'package:receiptbox/features/matching/domain/match_models.dart';
import 'package:receiptbox/features/transactions/domain/purchase_models.dart';

Map<String, dynamic> _transaction({String id = 'tx-1'}) => {
  'id': id,
  'merchant_display': 'Migros',
  'category_key': 'GROCERY',
  'purchase_date': '2026-11-14',
  'purchase_time': '18:27:00',
  'total_minor': 27030,
  'sources': ['RECEIPT', 'BANK_SCREENSHOT'],
};

Map<String, dynamic> _match({String id = 'd-1', String observation = 'o-1'}) =>
    {
      'id': id,
      'decision': 'PENDING',
      'score': 91.11,
      'features': {'date_diff_days': 1},
      'observation': {
        'id': observation,
        'source': 'BANK_SCREENSHOT',
        'merchant_display': 'MIGROS TICARET AS',
        'purchase_date': '2026-11-15',
        'purchase_time': null,
        'total_minor': 27030,
      },
      'transaction': _transaction(),
      'created_at': '2026-11-15T10:00:00Z',
    };

void main() {
  test('a suggestion is read with both sides', () {
    final suggestion = MatchSuggestion.fromJson(_match());

    expect(suggestion.id, 'd-1');
    expect(suggestion.score, closeTo(91.11, 0.001));
    expect(suggestion.observation.source, EvidenceKind.bank);
    expect(suggestion.observation.merchant, 'MIGROS TICARET AS');
    expect(suggestion.observation.date, DateTime(2026, 11, 15));
    expect(suggestion.observation.time, isNull);
    expect(suggestion.transaction.merchant, 'Migros');
    expect(suggestion.transaction.totalMinor, 27030);
    expect(suggestion.transaction.time!.hour, 18);
    expect(suggestion.transaction.time!.minute, 27);
    expect(suggestion.transaction.sources, [
      EvidenceKind.receipt,
      EvidenceKind.bank,
    ]);
  });

  test('suggestions are grouped by the waiting record', () {
    final groups = groupByObservation([
      MatchSuggestion.fromJson(_match(id: 'd-1', observation: 'o-1')),
      MatchSuggestion.fromJson(_match(id: 'd-2', observation: 'o-1')),
      MatchSuggestion.fromJson(_match(id: 'd-3', observation: 'o-2')),
    ]);

    expect(groups.keys, ['o-1', 'o-2']);
    expect(groups['o-1']!.map((m) => m.id), ['d-1', 'd-2']);
  });

  test('a bank row carries its match preview', () {
    final row = BankRow.fromJson({
      'observation_id': 'obs-1',
      'merchant_raw': 'MIGROS TICARET AS',
      'amount_minor': 27030,
      'direction': 'DEBIT',
      'kind': 'PURCHASE',
      'date': '2026-11-14',
      'status': 'PENDING_REVIEW',
      'confidence': {'merchant': 'HIGH'},
      'suggestions': {
        'category': {'key': 'OTHER'},
      },
      'match': {'state': 'AUTO', 'score': 100.0, 'transaction': _transaction()},
    });

    expect(row.match!.state, BankMatchState.auto);
    expect(row.match!.score, 100.0);
    expect(row.match!.transaction.merchant, 'Migros');
  });

  test('a SUGGEST preview and a row without a match', () {
    final suggested = BankRowMatch.fromJson({
      'state': 'SUGGEST',
      'score': 88.5,
      'transaction': _transaction(),
    });
    expect(suggested.state, BankMatchState.suggest);

    final plain = BankRow.fromJson({
      'observation_id': 'obs-2',
      'merchant_raw': 'BAMBASKA',
      'amount_minor': 100,
      'direction': 'DEBIT',
      'kind': 'PURCHASE',
      'status': 'PENDING_REVIEW',
    });
    expect(plain.match, isNull);
  });

  test('the batch answer lists merged and suggested rows', () {
    final result = BatchResult.fromJson({
      'created': [{}, {}],
      'skipped': [
        {'observation_id': 'o-9', 'reason': 'MISSING_DATE'},
      ],
      'merged': [
        {
          'observation_id': 'o-3',
          'match': {
            'decision_id': 'd-3',
            'decision': 'AUTO_ACCEPTED',
            'score': 100.0,
            'observation_id': 'o-3',
          },
          'transaction': {'id': 'tx-7'},
        },
      ],
      'suggested': [_match()],
    });

    expect(result.created, 2);
    expect(result.skipped, {'o-9': 'MISSING_DATE'});
    expect(result.merged.single.transactionId, 'tx-7');
    expect(result.merged.single.observationId, 'o-3');
    expect(result.suggested.single.id, 'd-1');
  });

  test('an older answer without merged and suggested still parses', () {
    final result = BatchResult.fromJson({'created': [], 'skipped': []});
    expect(result.merged, isEmpty);
    expect(result.suggested, isEmpty);
  });

  Map<String, dynamic> purchase({List<Map<String, dynamic>>? evidence}) => {
    ..._transaction(),
    'merchant_display': 'Migros',
    'currency': 'TRY',
    'payment_type': 'SINGLE',
    'channel': 'IN_STORE',
    'kind': 'PURCHASE',
    'is_estimated': false,
    'note': null,
    'document_count': 0,
    'created_at': '2026-11-14T18:30:00Z',
    'evidence':
        evidence ??
        [
          {'id': 'o-1', 'source': 'BANK_SCREENSHOT', 'amount_minor': 27050},
          {'id': 'o-2', 'source': 'RECEIPT', 'amount_minor': 27030},
        ],
    'items': [],
    'documents': [],
  };

  test('a purchase knows its records and whether it is a merge', () {
    final merged = PurchaseDetail.fromJson(purchase());
    expect(merged.isMerged, isTrue);
    expect(merged.evidence, [EvidenceKind.bank, EvidenceKind.receipt]);
    expect(merged.evidenceItems.map((e) => e.observationId), ['o-1', 'o-2']);
    expect(merged.evidenceItems.first.amountMinor, 27050);
    expect(merged.merge, isNull);

    final single = PurchaseDetail.fromJson(
      purchase(
        evidence: [
          {'id': 'o-1', 'source': 'RECEIPT', 'amount_minor': 27030},
        ],
      ),
    );
    expect(single.isMerged, isFalse);
  });

  test('a purchase that came out of a merge says how', () {
    final detail = PurchaseDetail.fromJson({
      ...purchase(),
      'outcome': 'MERGED',
      'match': {
        'decision_id': 'd-1',
        'decision': 'AUTO_ACCEPTED',
        'score': 100.0,
        'observation_id': 'o-2',
      },
    });
    expect(detail.merge!.isAuto, isTrue);
    expect(detail.merge!.observationId, 'o-2');

    final accepted = PurchaseDetail.fromJson({
      ...purchase(),
      'match': {
        'decision_id': 'd-1',
        'decision': 'ACCEPTED',
        'score': 90.0,
        'observation_id': 'o-2',
      },
    });
    expect(accepted.merge!.isAuto, isFalse);
  });

  test('the unmerge answer has both purchases', () {
    final result = UnmergeResult.fromJson({
      'transaction': purchase(),
      'new_transaction': purchase(),
    });
    expect(result.transaction.purchase.merchant, 'Migros');
    expect(result.newTransaction.purchase.id, 'tx-1');
  });
}
