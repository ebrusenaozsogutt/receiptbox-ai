import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/features/capture/domain/bank_models.dart';
import 'package:receiptbox/features/capture/domain/capture_payload.dart';
import 'package:receiptbox/features/capture/domain/extraction_result.dart';
import 'package:receiptbox/core/privacy/pii_masker.dart';
import 'package:receiptbox/features/installments/domain/installment_models.dart';
import 'package:receiptbox/features/matching/domain/match_models.dart';
import 'package:receiptbox/features/transactions/domain/purchase_models.dart';
import 'package:receiptbox/features/transactions/domain/spending_category.dart';

import '../../support/fakes.dart';

PlanPayment _payment(int seq, int month, PaymentStatus status) => PlanPayment(
  seq: seq,
  dueMonth: DateTime(2026, month),
  amountMinor: 208317,
  status: status,
);

InstallmentPlan _plan({PlanStatus status = PlanStatus.active}) =>
    InstallmentPlan(
      id: 'plan-1',
      count: 3,
      totalPayableMinor: 624951,
      firstDueMonth: DateTime(2026, 11),
      status: status,
      payments: [
        _payment(1, 11, PaymentStatus.inferred),
        _payment(2, 12, PaymentStatus.observed),
        _payment(3, 13, PaymentStatus.expected),
      ],
    );

InstallmentSchedule _schedule() => InstallmentSchedule(
  remainingMinor: 416634,
  months: [
    ScheduleMonth(
      month: DateTime(2026, 11),
      totalMinor: 208317,
      expectedMinor: 0,
      items: [
        ScheduleItem(
          transactionId: 'tx-1',
          merchant: 'MediaMarkt',
          seq: 1,
          count: 6,
          dueMonth: DateTime(2026, 11),
          amountMinor: 208317,
          status: PaymentStatus.observed,
          isEstimated: false,
        ),
      ],
    ),
    ScheduleMonth(
      month: DateTime(2026, 12),
      totalMinor: 208317,
      expectedMinor: 208317,
      items: [
        ScheduleItem(
          transactionId: 'tx-1',
          merchant: 'MediaMarkt',
          seq: 2,
          count: 6,
          dueMonth: DateTime(2026, 12),
          amountMinor: 208317,
          status: PaymentStatus.expected,
          isEstimated: true,
        ),
      ],
    ),
  ],
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

Future<TestApp> _openDetail(
  WidgetTester tester,
  PurchaseDetail Function(TestApp) seed,
) async {
  late String id;
  final app = await _openList(tester, seed: (a) => id = seed(a).purchase.id);
  await tester.tap(find.byKey(Key('purchase_$id')));
  await tester.pumpAndSettle();
  return app;
}

BankRow _bankRow(
  String id,
  String merchant,
  int amount, {
  int? seq,
  int? count,
  InstallmentPreview? installment,
}) => BankRow(
  observationId: id,
  merchant: merchant,
  amountMinor: amount,
  isCredit: false,
  kind: BankRowKind.purchase,
  date: DateTime(2026, 11, 12),
  installmentSeq: seq,
  installmentCount: count,
  isPending: false,
  isDuplicate: false,
  confidence: const {
    'merchant': 'HIGH',
    'amount': 'HIGH',
    'date': 'HIGH',
    'installment': 'HIGH',
  },
  category: SpendingCategory.other,
  installment: installment,
);

Future<TestApp> _openBank(WidgetTester tester, BankImport import) async {
  final app = await _signedIn(tester);
  app.extraction.bankResult = import;
  app.pipeline.result = CaptureResult(
    payload: CapturePayload(
      kind: CaptureKind.bankScreenshot,
      maskedText: 'BONUS DIJI\nGerçekleşen Hareketler',
      captureDate: DateTime(2026, 11, 14),
      source: CaptureSource.gallery,
    ),
    maskedCounts: const {PiiType.phone: 1},
    pageCount: 1,
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
  merchant: 'MEDIAMARKT',
  date: '2026-11-14',
  total: '12499.00',
  itemCount: 1,
  confidence: {
    'merchant': 'HIGH',
    'date': 'HIGH',
    'time': 'HIGH',
    'total': 'HIGH',
    'items': 'HIGH',
  },
  merchantMatch: 'GLOBAL_ALIAS',
  merchantName: 'MediaMarkt',
  categoryKey: 'TECHNOLOGY',
  categorySource: 'MERCHANT_DEFAULT',
  aiUsed: true,
  usedQr: false,
  time: '18:42:00',
  totalMinor: 1249900,
  lines: [ExtractedLine(name: 'TELEFON', totalMinor: 1249900)],
);

void main() {
  group('the installments screen', () {
    testWidgets('lists the payments by month with the remaining total', (
      tester,
    ) async {
      final app = await _openList(tester);
      app.transactions.scheduleAnswer = _schedule();

      await tester.tap(find.byKey(const Key('open_installments')));
      await tester.pumpAndSettle();

      expect(find.text('Kalan taksit toplamı'), findsOneWidget);
      expect(find.text('4.166,34 TL'), findsOneWidget);
      expect(find.byKey(const Key('schedule_month_2026-11')), findsOneWidget);
      expect(find.byKey(const Key('schedule_month_2026-12')), findsOneWidget);
      expect(find.text('Taksit 1/6 · Bankada görüldü'), findsOneWidget);
      expect(find.text('Taksit 2/6 · Bekleniyor'), findsOneWidget);
      expect(find.text('TAHMİNİ'), findsOneWidget);
      // payments, not spending
      expect(
        find.text(
          'Bunlar ödemelerdir; harcama alışveriş ayında bir kez sayılır.',
        ),
        findsOneWidget,
      );
    });

    testWidgets('says so when there is nothing to pay', (tester) async {
      await _openList(tester);

      await tester.tap(find.byKey(const Key('open_installments')));
      await tester.pumpAndSettle();

      expect(find.text('Taksitli alışveriş yok'), findsOneWidget);
    });
  });

  group('the purchase list', () {
    testWidgets('marks installment purchases and estimated ones', (
      tester,
    ) async {
      await _openList(
        tester,
        seed: (app) {
          app.transactions
            ..add(id: 'tx-1', merchant: 'MediaMarkt', plan: _plan())
            ..add(
              id: 'tx-2',
              merchant: 'TEKNOSA',
              evidence: const [EvidenceKind.bank],
              plan: _plan(),
              isEstimated: true,
            )
            ..add(id: 'tx-3', merchant: 'Migros');
        },
      );

      expect(find.byKey(const Key('installment_badge_tx-1')), findsOneWidget);
      expect(find.byKey(const Key('estimated_badge_tx-1')), findsNothing);
      expect(find.byKey(const Key('installment_badge_tx-2')), findsOneWidget);
      expect(find.byKey(const Key('estimated_badge_tx-2')), findsOneWidget);
      expect(find.byKey(const Key('installment_badge_tx-3')), findsNothing);
    });
  });

  group('the purchase detail', () {
    testWidgets('shows the plan: dots, months, amounts, the cancel button', (
      tester,
    ) async {
      await _openDetail(
        tester,
        (app) => app.transactions.add(
          id: 'tx-1',
          merchant: 'MediaMarkt',
          totalMinor: 624951,
          plan: _plan(),
        ),
      );

      expect(find.byKey(const Key('plan_card')), findsOneWidget);
      expect(find.text('3 TAKSİT'), findsOneWidget);
      expect(find.textContaining('1/3 taksit bankada görüldü'), findsOneWidget);
      expect(find.byKey(const Key('plan_payment_1')), findsOneWidget);
      expect(find.text('2. taksit · Aralık 2026'), findsOneWidget);
      expect(find.byKey(const Key('payment_dot_observed')), findsWidgets);
      expect(find.byKey(const Key('payment_dot_inferred')), findsWidgets);
      expect(find.byKey(const Key('payment_dot_expected')), findsWidgets);
      // a plan that has a bank row cannot be re-counted
      expect(find.byKey(const Key('plan_change')), findsNothing);
      expect(find.byKey(const Key('plan_cancel')), findsOneWidget);
    });

    testWidgets('several bank rows on one purchase: one chip, no "Ayır" on payments', (
      tester,
    ) async {
      await _openDetail(
        tester,
        (app) => app.transactions.add(
          id: 'tx-1',
          merchant: 'MediaMarkt',
          evidence: const [
            EvidenceKind.receipt,
            EvidenceKind.bank,
            EvidenceKind.bank,
          ],
          evidenceItems: const [
            EvidenceItem(
              observationId: 'o-receipt',
              kind: EvidenceKind.receipt,
              amountMinor: 1249900,
            ),
            EvidenceItem(
              observationId: 'o-b1',
              kind: EvidenceKind.bank,
              amountMinor: 208317,
              installmentSeq: 1,
              installmentCount: 6,
              isPayment: true,
            ),
            EvidenceItem(
              observationId: 'o-b2',
              kind: EvidenceKind.bank,
              amountMinor: 208317,
              installmentSeq: 2,
              installmentCount: 6,
              isPayment: true,
            ),
          ],
          plan: _plan(),
        ),
      );

      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('evidence_bank')), findsOneWidget);
      expect(find.text('Banka (2)'), findsOneWidget);
      // payments are not a second record of the purchase: nothing to separate
      expect(find.text('Birleşmiş kayıtlar'), findsNothing);
      expect(find.byKey(const Key('separate_o-b1')), findsNothing);
    });

    testWidgets('an estimated purchase says it waits for its receipt', (
      tester,
    ) async {
      await _openDetail(
        tester,
        (app) => app.transactions.add(
          id: 'tx-1',
          merchant: 'MEDIAMARKT',
          evidence: const [EvidenceKind.bank],
          plan: _plan(),
          isEstimated: true,
        ),
      );

      expect(find.text('TAHMİNİ'), findsOneWidget);
      expect(find.byKey(const Key('plan_estimated_note')), findsOneWidget);
    });

    testWidgets('"Taksitli yap" asks for the count and saves the plan', (
      tester,
    ) async {
      final app = await _openDetail(
        tester,
        (app) => app.transactions.add(id: 'tx-1', merchant: 'Teknosa'),
      );

      await tester.tap(find.byKey(const Key('plan_add')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('plan_plus')));
      await tester.pumpAndSettle();
      expect(find.text('4'), findsOneWidget);
      await tester.tap(find.byKey(const Key('plan_confirm')));
      await tester.pumpAndSettle();

      expect(app.transactions.plansPut.single, (
        transactionId: 'tx-1',
        count: 4,
      ));
    });

    testWidgets('the plan can be cancelled', (tester) async {
      final app = await _openDetail(
        tester,
        (app) => app.transactions.add(id: 'tx-1', plan: _plan()),
      );

      await tester.tap(find.byKey(const Key('plan_cancel')));
      await tester.pumpAndSettle();

      expect(app.transactions.plansCancelled.single, (
        planId: 'plan-1',
        cancel: true,
      ));
    });

    testWidgets('a refused change shows the server message', (tester) async {
      final app = await _openDetail(
        tester,
        (app) => app.transactions.add(id: 'tx-1', merchant: 'Teknosa'),
      );
      app.transactions.planError = apiError('NETWORK_UNREACHABLE');

      await tester.tap(find.byKey(const Key('plan_add')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('plan_confirm')));
      await tester.pumpAndSettle();

      expect(
        find.text(apiError('NETWORK_UNREACHABLE').message),
        findsOneWidget,
      );
    });
  });

  group('the receipt review', () {
    testWidgets('"Taksitli" sends the count with the confirmed purchase', (
      tester,
    ) async {
      final app = await _signedIn(tester);
      app.extraction.result = _extraction();
      app.pipeline.result = CaptureResult(
        payload: CapturePayload(
          kind: CaptureKind.receipt,
          maskedText: 'MEDIAMARKT\nTOPLAM 12.499,00',
          captureDate: DateTime(2026, 11, 14),
          source: CaptureSource.gallery,
        ),
        maskedCounts: const {},
        pageCount: 1,
      );
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

      await tester.tap(find.byKey(const Key('installment_switch')));
      await tester.pumpAndSettle();
      for (var i = 0; i < 3; i++) {
        await tester.tap(find.byKey(const Key('installment_plus')));
        await tester.pump();
      }
      expect(find.text('6 taksit'), findsOneWidget);
      await tester.tap(find.byKey(const Key('review_save')));
      await tester.pumpAndSettle();

      expect(app.transactions.confirmed.single.input.installmentCount, 6);
    });
  });

  group('the manual entry', () {
    testWidgets('"Taksitli" sends the count', (tester) async {
      final app = await _openList(tester);
      await tester.tap(find.byKey(const Key('add_manual_button')));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(const Key('field_merchant')),
        'Teknosa',
      );
      await tester.enterText(find.byKey(const Key('field_total')), '12.000');
      await tester.tap(find.byKey(const Key('installment_switch')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('installment_plus')));
      await tester.pump();
      await tester.tap(find.byKey(const Key('manual_save')));
      await tester.pumpAndSettle();

      expect(app.transactions.created.single.installmentCount, 4);
    });

    testWidgets('editing a saved purchase does not offer "Taksitli"', (
      tester,
    ) async {
      await _openDetail(
        tester,
        (app) => app.transactions.add(id: 'tx-1', merchant: 'Teknosa'),
      );

      await tester.tap(find.byKey(const Key('edit_button')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('installment_switch')), findsNothing);
    });
  });

  group('the bank import review', () {
    BankImport import() => BankImport(
      bankKey: BankKey.garanti,
      rows: [
        _bankRow(
          'r1',
          'MEDIAMARKT KONYA',
          208317,
          seq: 2,
          count: 6,
          installment: const InstallmentPreview(
            state: InstallmentPreviewState.link,
            seq: 2,
            count: 6,
            merchant: 'MediaMarkt',
          ),
        ),
        _bankRow(
          'r2',
          'TEKNOSA',
          100000,
          seq: 1,
          count: 3,
          installment: const InstallmentPreview(
            state: InstallmentPreviewState.estimate,
            seq: 1,
            count: 3,
            merchant: null,
          ),
        ),
      ],
      skipped: const [],
    );

    testWidgets(
      'an installment row has the TAKSİT badge and says what it becomes',
      (tester) async {
        await _openBank(tester, import());

        expect(find.text('TAKSİT 2/6'), findsOneWidget);
        expect(
          find.text('Taksit 2/6 → MediaMarkt alışverişine bağlanacak'),
          findsOneWidget,
        );
        expect(
          find.text('Taksit 1/3 → tahmini alışveriş oluşturulacak'),
          findsOneWidget,
        );
      },
    );

    testWidgets('saving reports the rows that became payments', (tester) async {
      final app = await _openBank(tester, import());
      app.transactions.add(id: 'tx-9');
      app.transactions.batchResult = const BatchResult(
        created: 0,
        skipped: {},
        linked: [
          LinkedRow(
            observationId: 'r1',
            seq: 2,
            count: 6,
            transactionId: 'tx-9',
          ),
        ],
      );

      await tester.tap(find.byKey(const Key('bank_save')));
      await tester.pumpAndSettle();

      expect(
        find.text('1 harcama kaydedildi, 1 taksit mevcut alışverişe bağlandı.'),
        findsOneWidget,
      );
    });
  });

  group('the installment question', () {
    MatchSuggestion suggestion({int? seq = 2, String id = 'd-1'}) =>
        MatchSuggestion(
          id: id,
          score: 80,
          observation: MatchObservation(
            id: 'o-1',
            source: EvidenceKind.bank,
            merchant: 'MEDIAMARKT KONYA',
            date: DateTime(2026, 11, 12),
            time: null,
            totalMinor: 208317,
          ),
          transaction: MatchTransaction(
            id: 'tx-9',
            merchant: 'MediaMarkt',
            category: SpendingCategory.technology,
            date: DateTime(2026, 10, 12),
            time: null,
            totalMinor: 1249900,
            sources: const [EvidenceKind.receipt],
          ),
          installmentSeq: seq,
          installmentCount: 6,
        );

    testWidgets('says "bağlansın mı" and answers with Bağla', (tester) async {
      final app = await _openBank(
        tester,
        BankImport(
          bankKey: BankKey.garanti,
          rows: [_bankRow('o-1', 'MEDIAMARKT KONYA', 208317)],
          skipped: const [],
        ),
      );
      app.transactions.batchResult = BatchResult(
        created: 0,
        skipped: const {},
        suggested: [suggestion(seq: null)],
      );

      await tester.tap(find.byKey(const Key('bank_save')));
      for (var i = 0; i < 10; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      expect(find.text('Bu bir taksit olabilir mi?'), findsOneWidget);
      expect(
        find.textContaining(
          'MediaMarkt alışverişinin 6 taksitinden biri olabilir',
        ),
        findsOneWidget,
      );
      expect(find.text('Bağla'), findsOneWidget);
      expect(find.text('Birleştir'), findsNothing);
    });
  });
}
