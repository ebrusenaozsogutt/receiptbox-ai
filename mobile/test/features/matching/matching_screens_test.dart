
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/core/networking/api_error.dart';
import 'package:receiptbox/core/privacy/pii_masker.dart';
import 'package:receiptbox/features/capture/domain/bank_models.dart';
import 'package:receiptbox/features/capture/domain/capture_payload.dart';
import 'package:receiptbox/features/capture/domain/extraction_result.dart';
import 'package:receiptbox/features/matching/domain/match_models.dart';
import 'package:receiptbox/features/transactions/domain/purchase_models.dart';
import 'package:receiptbox/features/transactions/domain/spending_category.dart';

import '../../support/fakes.dart';
import '../../support/purchase_fakes.dart';

// ---- data ----------------------------------------------------------------------------------

MatchTransaction _existing({
  String id = 'tx-9',
  String merchant = 'Migros',
  List<EvidenceKind> sources = const [EvidenceKind.receipt],
}) => MatchTransaction(
  id: id,
  merchant: merchant,
  category: SpendingCategory.grocery,
  date: DateTime(2026, 11, 14),
  time: const TimeOfDay(hour: 18, minute: 27),
  totalMinor: 27030,
  sources: sources,
);

MatchSuggestion _suggestion({
  String id = 'd-1',
  String observation = 'r3',
  MatchTransaction? transaction,
}) => MatchSuggestion(
  id: id,
  score: 91.1,
  observation: MatchObservation(
    id: observation,
    source: EvidenceKind.bank,
    merchant: 'MIGROS TICARET AS',
    date: DateTime(2026, 11, 15),
    time: null,
    totalMinor: 27030,
  ),
  transaction: transaction ?? _existing(),
);

BankRow _bankRow(
  String id,
  String merchant,
  int amount, {
  BankRowMatch? match,
}) => BankRow(
  observationId: id,
  merchant: merchant,
  amountMinor: amount,
  isCredit: false,
  kind: BankRowKind.purchase,
  date: DateTime(2026, 11, 12),
  installmentSeq: null,
  installmentCount: null,
  isPending: false,
  isDuplicate: false,
  confidence: const {
    'merchant': 'HIGH',
    'amount': 'HIGH',
    'date': 'HIGH',
    'installment': 'HIGH',
  },
  category: SpendingCategory.other,
  match: match,
);

BankImport _import() => BankImport(
  bankKey: BankKey.garanti,
  rows: [
    _bankRow(
      'r1',
      'MIGROS TICARET AS',
      27030,
      match: BankRowMatch(
        state: BankMatchState.auto,
        score: 100,
        transaction: _existing(),
      ),
    ),
    _bankRow(
      'r2',
      'ORNEK LOKANTA',
      6400,
      match: BankRowMatch(
        state: BankMatchState.suggest,
        score: 88,
        transaction: _existing(id: 'tx-8', merchant: 'Ornek Lokanta'),
      ),
    ),
    _bankRow('r3', 'BAMBASKA YER', 1234),
  ],
  skipped: const [],
);

// ---- opening the screens -----------------------------------------------------------------------

CaptureResult _captured(CaptureKind kind, String text) => CaptureResult(
  payload: CapturePayload(
    kind: kind,
    maskedText: text,
    captureDate: DateTime(2026, 11, 14),
    source: CaptureSource.gallery,
  ),
  maskedCounts: const {PiiType.phone: 1},
  pageCount: 1,
);

Future<TestApp> _signedIn(WidgetTester tester) async {
  tester.view.physicalSize = const Size(800, 2600);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final base = await TestApp.signedIn();
  final app = await TestApp.create(
    api: base.api,
    tokens: base.tokens,
    preferences: {
      'consent_seen': true,
      'has_account': true,
      'ai_consent': true,
    },
  );
  app.api.serverAiConsent = true;
  return app;
}

Future<TestApp> _openBank(WidgetTester tester, {BankImport? import}) async {
  final app = await _signedIn(tester);
  app.extraction.bankResult = import ?? _import();
  app.pipeline.result = _captured(
    CaptureKind.bankScreenshot,
    'BONUS DIJI\nGerçekleşen Hareketler\nHesap ve Kart',
  );
  await tester.pumpWidget(app.app());
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('nav_add_button')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('add_action_/capture/gallery')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('pick_image_button')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('kind_bank')));
  await tester.pumpAndSettle();
  return app;
}

ExtractionResult _extraction() => const ExtractionResult(
  observationId: 'obs-1',
  merchant: 'MIGROS TICARET A.S.',
  date: '2026-11-14',
  total: '270.30',
  itemCount: 1,
  confidence: {
    'merchant': 'HIGH',
    'date': 'HIGH',
    'time': 'HIGH',
    'total': 'HIGH',
    'items': 'HIGH',
  },
  merchantMatch: 'GLOBAL_ALIAS',
  merchantName: 'Migros',
  categoryKey: 'GROCERY',
  categorySource: 'MERCHANT_DEFAULT',
  aiUsed: true,
  usedQr: false,
  time: '18:42:00',
  totalMinor: 27030,
  lines: [ExtractedLine(name: 'SUT 1L', totalMinor: 27030)],
);

Future<TestApp> _openReview(WidgetTester tester) async {
  final app = await _signedIn(tester);
  app.extraction.result = _extraction();
  app.pipeline.result = _captured(CaptureKind.receipt, 'MIGROS\nTOPLAM 270,30');
  await tester.pumpWidget(app.app());
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('nav_add_button')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('add_action_/capture/gallery')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('pick_image_button')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('kind_receipt')));
  await tester.pumpAndSettle();
  return app;
}

Future<TestApp> _openList(
  WidgetTester tester, {
  void Function(TestApp app)? seed,
}) async {
  final app = await _signedIn(tester);
  seed?.call(app);
  await tester.pumpWidget(app.app());
  await tester.pumpAndSettle();
  await tester.tap(find.text('Harcamalar').last);
  await tester.pumpAndSettle();
  return app;
}

PurchaseDetail _mergedInto(TestApp app, {bool auto = true}) {
  final base = app.transactions.add(
    id: 'tx-9',
    evidence: const [EvidenceKind.bank, EvidenceKind.receipt],
    evidenceItems: const [
      EvidenceItem(
        observationId: 'o-bank',
        kind: EvidenceKind.bank,
        amountMinor: 27050,
      ),
      EvidenceItem(
        observationId: 'o-receipt',
        kind: EvidenceKind.receipt,
        amountMinor: 27030,
      ),
    ],
  );
  return PurchaseDetail(
    purchase: base.purchase,
    evidence: base.evidence,
    lines: const [],
    documents: const [],
    evidenceItems: base.evidenceItems,
    merge: MergeInfo(
      decisionId: 'd-1',
      observationId: 'o-receipt',
      isAuto: auto,
    ),
  );
}

/// While a save is running its spinner animates forever (also behind the open question sheet), so
/// `pumpAndSettle` never returns: pump a little instead.
Future<void> _pumpFor(WidgetTester tester) async {
  for (var i = 0; i < 10; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

final _bankSave = find.byKey(const Key('bank_save'));
final _reviewSave = find.byKey(const Key('review_save'));

void main() {
  group('the bank import review', () {
    testWidgets('rows that match a saved purchase say so', (tester) async {
      await _openBank(tester);

      expect(find.byKey(const Key('match_badge_r1')), findsOneWidget);
      expect(find.text('Eşleşti'), findsOneWidget);
      expect(find.text('Mevcut harcamayla birleşecek: Migros'), findsOneWidget);
      expect(find.byKey(const Key('match_badge_r2')), findsOneWidget);
      expect(find.text('Olası eşleşme'), findsOneWidget);
      expect(
        find.text('Kaydedince sorulacak: Ornek Lokanta ile aynı olabilir'),
        findsOneWidget,
      );
      expect(find.byKey(const Key('match_badge_r3')), findsNothing);
    });

    testWidgets('rows merged on saving are reported and can be undone', (
      tester,
    ) async {
      final app = await _openBank(tester);
      app.transactions.add(id: 'tx-9');
      app.transactions.batchResult = const BatchResult(
        created: 0,
        skipped: {},
        merged: [UndoableMerge(transactionId: 'tx-9', observationId: 'r1')],
      );

      await tester.tap(_bankSave);
      await tester.pumpAndSettle();

      expect(
        find.text('2 harcama kaydedildi, 1 satır mevcut harcamayla birleşti.'),
        findsOneWidget,
      );
      await tester.tap(find.text('Geri al'));
      await tester.pumpAndSettle();

      expect(app.transactions.unmerged.single, (
        transactionId: 'tx-9',
        observationId: 'r1',
      ));
      expect(find.text('Birleştirme geri alındı.'), findsOneWidget);
    });

    testWidgets('a row that may be the same asks after saving: Birleştir', (
      tester,
    ) async {
      final app = await _openBank(tester);
      app.transactions.batchResult = BatchResult(
        created: 0,
        skipped: const {},
        suggested: [_suggestion(id: 'd-1', observation: 'r2')],
      );

      await tester.tap(_bankSave);
      await _pumpFor(tester);

      expect(find.byKey(const Key('match_sheet')), findsOneWidget);
      expect(find.text('Aynı harcama olabilir mi?'), findsOneWidget);
      expect(
        find.text(
          'Bu işlem daha önce eklediğin Migros fişiyle aynı olabilir. '
          'Birleştirilsin mi?',
        ),
        findsOneWidget,
      );
      // the two records side by side
      expect(find.byKey(const Key('match_new')), findsOneWidget);
      expect(find.byKey(const Key('match_existing')), findsOneWidget);
      expect(
        find.descendant(
          of: find.byKey(const Key('match_new')),
          matching: find.text('MIGROS TICARET AS'),
        ),
        findsOneWidget,
      );
      expect(find.text('YENİ KAYIT'), findsOneWidget);
      expect(find.text('MEVCUT HARCAMA'), findsOneWidget);

      await tester.tap(find.byKey(const Key('match_accept_d-1')));
      await tester.pumpAndSettle();

      expect(app.transactions.accepted, ['d-1']);
      expect(app.transactions.rejectedMatches, isEmpty);
      expect(
        find.text('2 harcama kaydedildi, 1 satır mevcut harcamayla birleşti.'),
        findsOneWidget,
      );
    });

    testWidgets('Ayrı kalsın makes it a purchase of its own', (tester) async {
      final app = await _openBank(tester);
      app.transactions.batchResult = BatchResult(
        created: 0,
        skipped: const {},
        suggested: [_suggestion(id: 'd-1', observation: 'r2')],
      );

      await tester.tap(_bankSave);
      await _pumpFor(tester);
      await tester.tap(find.byKey(const Key('match_reject')));
      await tester.pumpAndSettle();

      expect(app.transactions.rejectedMatches, ['d-1']);
      expect(app.transactions.accepted, isEmpty);
      expect(find.text('3 harcama kaydedildi.'), findsOneWidget);
    });

    testWidgets('closing the question leaves it open for later', (
      tester,
    ) async {
      final app = await _openBank(tester);
      app.transactions.batchResult = BatchResult(
        created: 0,
        skipped: const {},
        suggested: [_suggestion(id: 'd-1', observation: 'r2')],
      );
      app.transactions.pending = [_suggestion(id: 'd-1', observation: 'r2')];

      await tester.tap(_bankSave);
      await _pumpFor(tester);
      await tester.tapAt(const Offset(10, 10)); // outside the sheet
      await _pumpFor(tester);
      await tester.pumpAndSettle();

      expect(app.transactions.accepted, isEmpty);
      expect(app.transactions.rejectedMatches, isEmpty);
      // back on the list, the question is offered again
      expect(find.byKey(const Key('pending_matches_banner')), findsOneWidget);
      expect(find.text('1 eşleşme önerisi bekliyor'), findsOneWidget);
    });
  });

  group('the question sheet', () {
    testWidgets('several candidates: pick one, or none', (tester) async {
      final app = await _openBank(tester);
      app.transactions.batchResult = BatchResult(
        created: 0,
        skipped: const {},
        suggested: [
          _suggestion(id: 'd-1', observation: 'r2'),
          _suggestion(
            id: 'd-2',
            observation: 'r2',
            transaction: _existing(
              id: 'tx-10',
              sources: const [EvidenceKind.bank],
            ),
          ),
        ],
      );

      await tester.tap(_bankSave);
      await _pumpFor(tester);

      expect(
        find.text(
          'Bu işlem daha önce eklediğin birkaç harcamayla aynı olabilir. '
          'Hangisiyle birleştirilsin?',
        ),
        findsOneWidget,
      );
      expect(find.byKey(const Key('match_candidate_d-1')), findsOneWidget);
      expect(find.byKey(const Key('match_candidate_d-2')), findsOneWidget);

      await tester.tap(find.byKey(const Key('match_accept_d-2')));
      await tester.pumpAndSettle();

      expect(app.transactions.accepted, ['d-2']);
    });

    testWidgets('an answer the server refuses is shown and the sheet stays', (
      tester,
    ) async {
      final app = await _openBank(tester);
      app.transactions.batchResult = BatchResult(
        created: 0,
        skipped: const {},
        suggested: [_suggestion(id: 'd-1', observation: 'r2')],
      );
      app.transactions.matchError = fakeApiError(
        'MATCH_NOT_AVAILABLE',
        status: 409,
      );

      await tester.tap(_bankSave);
      await _pumpFor(tester);
      await tester.tap(find.byKey(const Key('match_accept_d-1')));
      await _pumpFor(tester);

      expect(find.byKey(const Key('match_sheet')), findsOneWidget);
      expect(find.text(messageForCode('MATCH_NOT_AVAILABLE')), findsOneWidget);
      expect(app.transactions.accepted, isEmpty);

      app.transactions.matchError = null;
      await tester.tap(find.byKey(const Key('match_accept_d-1')));
      await tester.pumpAndSettle();
      expect(app.transactions.accepted, ['d-1']);
    });
  });

  group('the receipt review', () {
    testWidgets('a receipt merged automatically offers Geri al', (
      tester,
    ) async {
      final app = await _openReview(tester);
      app.transactions.nextSave = Saved(_mergedInto(app));

      await tester.tap(_reviewSave);
      await tester.pumpAndSettle();

      expect(
        find.text('Bu fiş mevcut bir harcamayla eşleşti ve birleştirildi.'),
        findsOneWidget,
      );
      await tester.tap(find.text('Geri al'));
      await tester.pumpAndSettle();

      expect(app.transactions.unmerged.single, (
        transactionId: 'tx-9',
        observationId: 'o-receipt',
      ));
      expect(find.text('Birleştirme geri alındı.'), findsOneWidget);
    });

    testWidgets('Geri al closes by itself after about 6 seconds', (tester) async {
      final app = await _openReview(tester);
      app.transactions.nextSave = Saved(_mergedInto(app));
      const text = 'Bu fiş mevcut bir harcamayla eşleşti ve birleştirildi.';

      await tester.tap(_reviewSave);
      await tester.pumpAndSettle();
      expect(find.text(text), findsOneWidget);

      await tester.pump(const Duration(seconds: 5));
      expect(find.text(text), findsOneWidget); // still there to be undone
      await tester.pump(const Duration(seconds: 2));
      await tester.pumpAndSettle();
      expect(find.text(text), findsNothing); // an action no longer keeps it forever
    });

    testWidgets('opening another page closes Geri al: it never covers Kaydet', (
      tester,
    ) async {
      final app = await _openReview(tester);
      app.transactions.nextSave = Saved(_mergedInto(app));
      const text = 'Bu fiş mevcut bir harcamayla eşleşti ve birleştirildi.';

      await tester.tap(_reviewSave);
      await tester.pumpAndSettle();
      expect(find.text(text), findsOneWidget); // shown on the list after saving

      await tester.tap(find.byKey(const Key('add_manual_button')));
      await tester.pumpAndSettle();

      expect(find.text(text), findsNothing);
      expect(find.text('Geri al'), findsNothing);
      expect(find.byKey(const Key('manual_save')).hitTestable(), findsOneWidget);
    });

    testWidgets('switching tabs closes Geri al', (tester) async {
      final app = await _openReview(tester);
      app.transactions.nextSave = Saved(_mergedInto(app));

      await tester.tap(_reviewSave);
      await tester.pumpAndSettle();
      expect(find.text('Geri al'), findsOneWidget);

      await tester.tap(find.text('Ana Sayfa').last);
      await tester.pumpAndSettle();

      expect(find.text('Geri al'), findsNothing);
    });

    testWidgets('a receipt that may be a saved purchase asks first', (
      tester,
    ) async {
      final app = await _openReview(tester);
      app.transactions.nextSave = NeedsAnswer([
        _suggestion(id: 'd-5', observation: 'obs-1'),
      ]);

      await tester.tap(_reviewSave);
      await _pumpFor(tester);

      expect(find.byKey(const Key('match_sheet')), findsOneWidget);
      // nothing was created while the question is open
      expect(app.transactions.purchases, isEmpty);
      app.transactions.matchAnswer = _mergedInto(app);

      await tester.tap(find.byKey(const Key('match_accept_d-5')));
      await tester.pumpAndSettle();

      expect(app.transactions.accepted, ['d-5']);
      expect(find.text('Mevcut harcamayla birleştirildi.'), findsOneWidget);
    });

    testWidgets('Ayrı kalsın saves the receipt as its own purchase', (
      tester,
    ) async {
      final app = await _openReview(tester);
      app.transactions.nextSave = NeedsAnswer([
        _suggestion(id: 'd-5', observation: 'obs-1'),
      ]);

      await tester.tap(_reviewSave);
      await _pumpFor(tester);
      await tester.tap(find.byKey(const Key('match_reject')));
      await tester.pumpAndSettle();

      expect(app.transactions.rejectedMatches, ['d-5']);
      expect(find.text('Harcama kaydedildi.'), findsOneWidget);
    });
  });

  group('the purchase list', () {
    testWidgets('a waiting question shows a banner that opens it', (
      tester,
    ) async {
      final app = await _openList(
        tester,
        seed: (app) {
          app.transactions.add(id: 'tx-9', merchant: 'Migros');
          app.transactions.pending = [_suggestion()];
        },
      );

      expect(find.text('1 eşleşme önerisi bekliyor'), findsOneWidget);
      await tester.tap(find.byKey(const Key('pending_matches_banner')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('match_sheet')), findsOneWidget);

      await tester.tap(find.byKey(const Key('match_accept_d-1')));
      await tester.pumpAndSettle();

      expect(app.transactions.accepted, ['d-1']);
      expect(find.text('Birleştirildi.'), findsOneWidget);
      expect(find.byKey(const Key('pending_matches_banner')), findsNothing);
    });

    testWidgets('no banner when nothing waits', (tester) async {
      await _openList(tester, seed: (app) => app.transactions.add());
      expect(find.byKey(const Key('pending_matches_banner')), findsNothing);
    });

    testWidgets('two waiting records are counted as two questions', (
      tester,
    ) async {
      await _openList(
        tester,
        seed: (app) {
          app.transactions.pending = [
            _suggestion(id: 'd-1', observation: 'o-1'),
            _suggestion(
              id: 'd-2',
              observation: 'o-1',
            ), // same record, two candidates
            _suggestion(id: 'd-3', observation: 'o-2'),
          ];
        },
      );
      expect(find.text('2 eşleşme önerisi bekliyor'), findsOneWidget);
    });
  });

  group('the purchase detail', () {
    testWidgets('a merged purchase lists its records, each can be separated', (
      tester,
    ) async {
      final app = await _openList(tester, seed: (app) => _mergedInto(app));
      await tester.tap(find.text('Migros'));
      await tester.pumpAndSettle();

      expect(find.text('Birleşmiş kayıtlar'), findsOneWidget);
      expect(
        find.text('Banka · 270,50 TL'),
        findsOneWidget,
      ); // the bank amount is evidence
      expect(find.text('Fiş · 270,30 TL'), findsOneWidget);

      await tester.tap(find.byKey(const Key('separate_o-bank')));
      await tester.pumpAndSettle();
      expect(find.text('Banka kaydı ayrılsın mı?'), findsOneWidget);
      await tester.tap(find.byKey(const Key('separate_confirm')));
      await tester.pumpAndSettle();

      expect(app.transactions.unmerged.single, (
        transactionId: 'tx-9',
        observationId: 'o-bank',
      ));
      expect(
        find.text('Kayıtlar ayrıldı: iki ayrı harcama var.'),
        findsOneWidget,
      );
    });

    testWidgets('Vazgeç keeps the purchase merged', (tester) async {
      final app = await _openList(tester, seed: (app) => _mergedInto(app));
      await tester.tap(find.text('Migros'));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('separate_o-receipt')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Vazgeç'));
      await tester.pumpAndSettle();

      expect(app.transactions.unmerged, isEmpty);
    });

    testWidgets('a purchase with one record has no Ayır', (tester) async {
      await _openList(
        tester,
        seed: (app) => app.transactions.add(
          id: 'tx-1',
          evidenceItems: const [
            EvidenceItem(
              observationId: 'o-1',
              kind: EvidenceKind.receipt,
              amountMinor: 27030,
            ),
          ],
        ),
      );
      await tester.tap(find.text('Migros'));
      await tester.pumpAndSettle();

      expect(find.text('Birleşmiş kayıtlar'), findsNothing);
      expect(find.byKey(const Key('separate_o-1')), findsNothing);
    });
  });

  group('the manual form', () {
    testWidgets('a manual entry that may be a saved purchase asks first', (
      tester,
    ) async {
      final app = await _openList(
        tester,
        seed: (app) => app.transactions.nextSave = NeedsAnswer([
          _suggestion(id: 'd-7', observation: 'm-1'),
        ]),
      );
      await tester.tap(find.byKey(const Key('add_manual_button')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const Key('field_merchant')), 'Migros');
      await tester.enterText(find.byKey(const Key('field_total')), '1.249,90');
      await tester.pump(); // the save button follows the typed values
      await tester.tap(find.byKey(const Key('manual_save')));
      await _pumpFor(tester);

      expect(find.byKey(const Key('match_sheet')), findsOneWidget);
      await tester.tap(find.byKey(const Key('match_reject')));
      await tester.pumpAndSettle();

      expect(app.transactions.rejectedMatches, ['d-7']);
      expect(find.text('Harcama kaydedildi.'), findsOneWidget);
    });

    testWidgets('a manual entry merged automatically offers Geri al', (
      tester,
    ) async {
      final app = await _openList(
        tester,
        seed: (app) {
          // the scripted answer is created lazily: the purchase must exist for the undo
          app.transactions.add(id: 'tx-9');
        },
      );
      app.transactions.nextSave = Saved(
        PurchaseDetail(
          purchase: app.transactions.purchases.first.purchase,
          evidence: const [EvidenceKind.bank, EvidenceKind.manual],
          lines: const [],
          documents: const [],
          merge: const MergeInfo(
            decisionId: 'd-2',
            observationId: 'o-manual',
            isAuto: true,
          ),
        ),
      );
      await tester.tap(find.byKey(const Key('add_manual_button')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const Key('field_merchant')), 'Migros');
      await tester.enterText(find.byKey(const Key('field_total')), '1.249,90');
      await tester.pump(); // the save button follows the typed values
      await tester.tap(find.byKey(const Key('manual_save')));
      await tester.pumpAndSettle();

      expect(
        find.text('Bu harcama mevcut bir kayıtla eşleşti ve birleştirildi.'),
        findsOneWidget,
      );
      await tester.tap(find.text('Geri al'));
      await tester.pumpAndSettle();
      expect(app.transactions.unmerged.single.observationId, 'o-manual');
    });
  });

  test('the new error codes have Turkish messages', () {
    for (final code in [
      'MATCH_NOT_PENDING',
      'MATCH_NOT_AVAILABLE',
      'NOT_MERGED',
    ]) {
      expect(messageForCode(code), isNot(messageForCode('SOMETHING_ELSE')));
    }
  });
}
