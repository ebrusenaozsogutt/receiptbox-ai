import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/features/capture/domain/bank_models.dart';
import 'package:receiptbox/features/transactions/domain/spending_category.dart';

Map<String, dynamic> _row({
  String merchant = 'MIGROS',
  int amount = 16128,
  String direction = 'DEBIT',
  String kind = 'PURCHASE',
  String? date = '2026-11-12',
  int? seq,
  int? count,
  bool pending = false,
  String status = 'PENDING_REVIEW',
  Map<String, String>? confidence,
  String category = 'GROCERY',
}) => {
  'observation_id': 'obs-1',
  'merchant_raw': merchant,
  'amount_minor': amount,
  'direction': direction,
  'kind': kind,
  'date': date,
  'time': null,
  'installment_seq': seq,
  'installment_count': count,
  'is_pending': pending,
  'status': status,
  'possible_refund': kind == 'REFUND',
  'confidence':
      confidence ??
      {
        'merchant': 'HIGH',
        'amount': 'HIGH',
        'date': 'HIGH',
        'installment': 'HIGH',
      },
  'suggestions': {
    'merchant': {'match': 'NONE'},
    'category': {'key': category, 'source': 'FALLBACK'},
  },
};

void main() {
  group('BankRow.fromJson', () {
    test('a purchase', () {
      final row = BankRow.fromJson(_row(seq: 2, count: 3));

      expect(row.merchant, 'MIGROS');
      expect(row.amountMinor, 16128);
      expect(row.isCredit, isFalse);
      expect(row.kind, BankRowKind.purchase);
      expect(row.date, DateTime(2026, 11, 12));
      expect(row.installmentLabel, '2/3');
      expect(row.category, SpendingCategory.grocery);
      expect(row.isSelectable, isTrue);
      expect(row.needsCheck, isFalse);
    });

    test('a possible refund is not selectable', () {
      final row = BankRow.fromJson(_row(direction: 'CREDIT', kind: 'REFUND'));
      expect(row.isCredit, isTrue);
      expect(row.kind, BankRowKind.refund);
      expect(row.isSelectable, isFalse);
    });

    test('a duplicate is not selectable', () {
      expect(BankRow.fromJson(_row(status: 'DUPLICATE')).isSelectable, isFalse);
    });

    test('a count without a position reads "3 taksit"', () {
      expect(BankRow.fromJson(_row(count: 3)).installmentLabel, '3 taksit');
      expect(BankRow.fromJson(_row()).installmentLabel, isNull);
    });

    test('a missing date stays null and needs a check', () {
      final row = BankRow.fromJson(
        _row(
          date: null,
          confidence: {
            'merchant': 'HIGH',
            'amount': 'HIGH',
            'date': 'LOW',
            'installment': 'HIGH',
          },
        ),
      );
      expect(row.date, isNull);
      expect(row.needsCheck, isTrue);
    });

    test('an unsure merchant needs a check', () {
      final row = BankRow.fromJson(
        _row(confidence: {'merchant': 'MEDIUM', 'date': 'HIGH'}),
      );
      expect(row.needsCheck, isTrue);
    });

    test('an unknown category falls back to Diğer', () {
      expect(
        BankRow.fromJson(_row(category: 'SOMETHING')).category,
        SpendingCategory.other,
      );
    });

    test('pending flag', () {
      expect(BankRow.fromJson(_row(pending: true)).isPending, isTrue);
    });
  });

  group('SkippedRow', () {
    test('reason labels are Turkish', () {
      String label(String reason) =>
          SkippedRow(merchant: 'x', amountMinor: 1, reason: reason).reasonLabel;
      expect(label('PAYMENT'), 'Kart ödemesi');
      expect(label('NON_TL_AMOUNT'), 'Puan / TL olmayan tutar');
      expect(label('ZERO_AMOUNT'), 'Tutarı yok (0,00)');
      expect(label('HEADER_OR_TOTAL'), 'Toplam / başlık satırı');
      expect(label('AMOUNT_NOT_IN_TEXT'), 'Okunamadı');
    });
  });

  test('BankImport.fromJson reads the bank, rows and skipped rows', () {
    final import = BankImport.fromJson({
      'bank_key': 'akbank',
      'rows': [_row()],
      'skipped': [
        {
          'merchant_raw': 'Cep Şube Ödeme',
          'amount_minor': 100,
          'date': null,
          'reason': 'PAYMENT',
        },
      ],
    });

    expect(import.bankKey, BankKey.akbank);
    expect(import.rows, hasLength(1));
    expect(import.skipped.single.reason, 'PAYMENT');
  });

  test('a bank without help has no key', () {
    expect(
      BankImport.fromJson({'bank_key': null, 'rows': [], 'skipped': []})
          .bankKey,
      isNull,
    );
  });

  test('BatchResult.fromJson', () {
    final result = BatchResult.fromJson({
      'created': [{}, {}],
      'skipped': [
        {'observation_id': 'a', 'reason': 'POSSIBLE_REFUND'},
      ],
    });
    expect(result.created, 2);
    expect(result.skipped, {'a': 'POSSIBLE_REFUND'});
  });
}
