import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart' show TimeOfDay;
import 'package:receiptbox/features/capture/domain/capture_payload.dart';
import 'package:receiptbox/features/capture/domain/extraction_result.dart';
import 'package:receiptbox/features/capture/domain/review_form.dart';
import 'package:receiptbox/features/transactions/domain/spending_category.dart';

CapturePayload _payload({Map<String, dynamic>? qr}) => CapturePayload(
  kind: CaptureKind.receipt,
  maskedText: 'x',
  qrPayload: qr,
  captureDate: DateTime(2026, 11, 18),
  source: CaptureSource.gallery,
);

ExtractionResult _result({
  Map<String, String> confidence = const {
    'merchant': 'HIGH',
    'date': 'HIGH',
    'time': 'HIGH',
    'total': 'HIGH',
    'items': 'HIGH',
  },
  String? merchant = 'MIGROS TICARET A.S.',
  String? date = '2026-11-14',
  String? time = '18:42:00',
  int? totalMinor = 27030,
  String merchantMatch = 'GLOBAL_ALIAS',
  String? merchantName = 'Migros',
  String categorySource = 'MERCHANT_DEFAULT',
  List<ExtractedLine> lines = const [
    ExtractedLine(name: 'SUT', totalMinor: 10000),
    ExtractedLine(name: 'EKMEK', totalMinor: 17030),
  ],
}) => ExtractionResult(
  observationId: 'obs-1',
  merchant: merchant,
  date: date,
  total: '270.30',
  itemCount: lines.length,
  confidence: confidence,
  merchantMatch: merchantMatch,
  merchantName: merchantName,
  categoryKey: 'GROCERY',
  categorySource: categorySource,
  aiUsed: true,
  usedQr: false,
  time: time,
  totalMinor: totalMinor,
  lines: lines,
);

void main() {
  group('ReviewForm.fromExtraction', () {
    test('everything HIGH and a known merchant: nothing is flagged', () {
      final form = ReviewForm.fromExtraction(_result(), _payload());

      expect(form.merchant, 'Migros'); // the known merchant's name, not the raw text
      expect(form.date, DateTime(2026, 11, 14));
      expect(form.time, const TimeOfDay(hour: 18, minute: 42));
      expect(form.totalMinor, 27030);
      expect(form.category, SpendingCategory.grocery);
      expect(form.channel, PurchaseChannel.inStore);
      expect(form.flagged, isEmpty);
      expect(form.pendingChecks, 0);
      expect(form.canSave, isTrue);
    });

    test('MEDIUM and LOW fields are flagged, HIGH ones are not', () {
      final form = ReviewForm.fromExtraction(
        _result(
          confidence: const {
            'merchant': 'MEDIUM',
            'date': 'HIGH',
            'time': 'LOW',
            'total': 'HIGH',
            'items': 'LOW',
          },
        ),
        _payload(),
      );

      expect(form.flagged, {ReviewField.merchant, ReviewField.time});
      expect(form.linesFlagged, isTrue);
      expect(form.pendingChecks, 3);
    });

    test('a category that is only a guess is flagged', () {
      final form = ReviewForm.fromExtraction(
        _result(categorySource: 'LLM'),
        _payload(),
      );
      expect(form.flagged, contains(ReviewField.category));
    });

    test('missing values are flagged, and a missing time is simply empty', () {
      final form = ReviewForm.fromExtraction(
        _result(merchant: null, merchantMatch: 'NONE', merchantName: null, date: null, time: null, totalMinor: null),
        _payload(),
      );

      expect(form.merchant, '');
      expect(form.date, DateTime(2026, 11, 18)); // falls back to the capture date
      expect(form.time, isNull);
      expect(form.flagged, containsAll({ReviewField.merchant, ReviewField.date, ReviewField.total}));
      expect(form.flagged, isNot(contains(ReviewField.time)));
      expect(form.canSave, isFalse);
    });

    test('an e-invoice QR means the purchase was made online', () {
      final form = ReviewForm.fromExtraction(
        _result(),
        _payload(qr: const {'ettn': 'abc'}),
      );
      expect(form.channel, PurchaseChannel.online);
    });
  });

  group('ReviewForm.empty / blank', () {
    test('empty (nothing could be read) flags the four required fields', () {
      final form = ReviewForm.empty(_payload());
      expect(form.flagged, {
        ReviewField.merchant,
        ReviewField.date,
        ReviewField.total,
        ReviewField.category,
      });
      expect(form.canSave, isFalse);
    });

    test('blank (manual entry) flags nothing', () {
      final form = ReviewForm.blank(DateTime(2026, 11, 18, 14, 30));
      expect(form.flagged, isEmpty);
      expect(form.date, DateTime(2026, 11, 18));
      expect(form.canSave, isFalse);
    });
  });

  group('itemsSumCheck', () {
    const lines = [
      EditableLine(name: 'a', totalMinor: 10000),
      EditableLine(name: 'b', totalMinor: 17030),
    ];

    test('lines that add up to the total match', () {
      expect(itemsSumCheck(lines, 27030), SumCheck.matches);
    });

    test('a small rounding difference is tolerated (0,05 TL or 1%)', () {
      expect(itemsSumCheck(lines, 27035), SumCheck.matches);
      expect(itemsSumCheck(lines, 27030 + 270), SumCheck.matches); // 1% of the total
    });

    test('a bigger difference is reported', () {
      expect(itemsSumCheck(lines, 30000), SumCheck.differs);
    });

    test('a line without an amount cannot be checked', () {
      expect(
        itemsSumCheck([...lines, const EditableLine(name: 'c')], 27030),
        SumCheck.incomplete,
      );
    });

    test('no lines or no total says nothing', () {
      expect(itemsSumCheck(const [], 27030), SumCheck.none);
      expect(itemsSumCheck(lines, null), SumCheck.none);
    });
  });
}
