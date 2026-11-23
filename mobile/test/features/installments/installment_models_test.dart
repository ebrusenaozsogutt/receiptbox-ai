import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/features/installments/domain/installment_models.dart';
import 'package:receiptbox/features/matching/domain/match_models.dart';

Map<String, dynamic> _plan() => {
  'id': 'plan-1',
  'count': 3,
  'total_payable_minor': 30000,
  'first_due_month': '2026-11-01',
  'status': 'ACTIVE',
  'payments': [
    {
      'seq': 1,
      'due_month': '2026-11-01',
      'amount_minor': 10000,
      'status': 'INFERRED',
    },
    {
      'seq': 2,
      'due_month': '2026-12-01',
      'amount_minor': 10000,
      'status': 'OBSERVED',
    },
    {
      'seq': 3,
      'due_month': '2027-01-01',
      'amount_minor': 10000,
      'status': 'EXPECTED',
    },
  ],
};

void main() {
  group('InstallmentPlan', () {
    test('reads the payments and their statuses', () {
      final plan = InstallmentPlan.fromJson(_plan());

      expect(plan.count, 3);
      expect(plan.isActive, isTrue);
      expect(plan.firstDueMonth, DateTime(2026, 11, 1));
      expect(plan.payments.map((p) => p.status), [
        PaymentStatus.inferred,
        PaymentStatus.observed,
        PaymentStatus.expected,
      ]);
      // only a bank row that was really seen counts as observed
      expect(plan.observedCount, 1);
    });

    test('unknown statuses fall back to the quiet ones', () {
      expect(PaymentStatus.fromKey('???'), PaymentStatus.expected);
      expect(PlanStatus.fromKey('???'), PlanStatus.active);
      expect(PlanStatus.fromKey('CANCELLED'), PlanStatus.cancelled);
      expect(PlanStatus.fromKey('COMPLETED'), PlanStatus.completed);
    });
  });

  group('InstallmentSchedule', () {
    Map<String, dynamic> json({List<Map<String, dynamic>> items = const []}) =>
        {
          'remaining_minor': 20000,
          'months': [
            {
              'month': '2026-11-01',
              'total_minor': items.isEmpty ? 0 : 10000,
              'expected_minor': 0,
              'items': items,
            },
          ],
        };

    test('is empty when no month has a payment', () {
      expect(InstallmentSchedule.fromJson(json()).isEmpty, isTrue);
    });

    test('reads the items of a month', () {
      final schedule = InstallmentSchedule.fromJson(
        json(
          items: [
            {
              'transaction_id': 'tx-1',
              'merchant_display': 'MediaMarkt',
              'seq': 2,
              'count': 6,
              'due_month': '2026-11-01',
              'amount_minor': 10000,
              'status': 'OBSERVED',
              'is_estimated': true,
            },
          ],
        ),
      );

      expect(schedule.isEmpty, isFalse);
      expect(schedule.remainingMinor, 20000);
      final item = schedule.months.single.items.single;
      expect(item.merchant, 'MediaMarkt');
      expect(item.isEstimated, isTrue);
      expect(item.status, PaymentStatus.observed);
    });
  });

  group('InstallmentPreview', () {
    InstallmentPreview preview(String state, {String? merchant}) =>
        InstallmentPreview.fromJson({
          'state': state,
          'seq': 2,
          'count': 6,
          'transaction': merchant == null
              ? null
              : {'merchant_display': merchant},
        });

    test('says which purchase the row will join', () {
      expect(
        preview('LINK', merchant: 'MediaMarkt').label,
        'Taksit 2/6 → MediaMarkt alışverişine bağlanacak',
      );
    });

    test('says an estimated purchase will be made when there is none', () {
      expect(
        preview('ESTIMATE').label,
        'Taksit 2/6 → tahmini alışveriş oluşturulacak',
      );
    });

    test('says it will ask when several purchases fit', () {
      expect(
        preview('ASK').label,
        'Taksit 2/6 → birden fazla alışverişe uyuyor, kaydedince sorulacak',
      );
    });

    test('a row without a marker is only a suggestion', () {
      expect(
        preview('SUGGEST', merchant: 'MediaMarkt').label,
        'Bir taksit olabilir (MediaMarkt · 6 taksit): kaydedince sorulacak',
      );
    });
  });

  group('MatchSuggestion', () {
    Map<String, dynamic> json(String type) => {
      'id': 'd-1',
      'score': 80.0,
      'match_type': type,
      'installment_seq': 2,
      'installment_count': 6,
      'observation': {
        'id': 'o-1',
        'source': 'BANK_SCREENSHOT',
        'merchant_display': 'MEDIAMARKT KONYA',
        'purchase_date': '2026-11-12',
        'purchase_time': null,
        'total_minor': 208317,
      },
      'transaction': {
        'id': 'tx-1',
        'merchant_display': 'MediaMarkt',
        'category_key': 'TECHNOLOGY',
        'purchase_date': '2026-10-12',
        'purchase_time': null,
        'total_minor': 1249900,
        'sources': ['RECEIPT'],
      },
    };

    test('an installment suggestion knows its position', () {
      final s = MatchSuggestion.fromJson(json('INSTALLMENT'));
      expect(s.isInstallment, isTrue);
      expect(s.installmentSeq, 2);
      expect(s.installmentCount, 6);
    });

    test('a 1:1 suggestion is not an installment one', () {
      final s = MatchSuggestion.fromJson(json('SAME_PURCHASE'));
      expect(s.isInstallment, isFalse);
      expect(s.installmentCount, isNull);
    });
  });
}
