import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/core/networking/api_error.dart';
import 'package:receiptbox/features/capture/domain/bank_models.dart';
import 'package:receiptbox/features/capture/domain/capture_payload.dart';
import 'package:receiptbox/features/transactions/domain/spending_category.dart';

import '../../support/fakes.dart';
import '../../support/purchase_fakes.dart';

BankRow row(
  String id,
  String merchant,
  int amount, {
  DateTime? date,
  bool credit = false,
  BankRowKind kind = BankRowKind.purchase,
  int? seq,
  int? count,
  bool pending = false,
  bool duplicate = false,
  Map<String, String>? confidence,
  SpendingCategory category = SpendingCategory.other,
  bool noDate = false,
}) => BankRow(
  observationId: id,
  merchant: merchant,
  amountMinor: amount,
  isCredit: credit,
  kind: kind,
  date: noDate ? null : (date ?? DateTime(2026, 11, 12)),
  installmentSeq: seq,
  installmentCount: count,
  isPending: pending,
  isDuplicate: duplicate,
  confidence:
      confidence ??
      const {
        'merchant': 'HIGH',
        'amount': 'HIGH',
        'date': 'HIGH',
        'installment': 'HIGH',
      },
  category: category,
);

final _garanti = BankImport(
  bankKey: BankKey.garanti,
  rows: [
    row(
      'r1',
      'MIGROS',
      16128,
      seq: 2,
      count: 3,
      category: SpendingCategory.grocery,
    ),
    row('r2', 'TRENDYOL.COM', 63957, pending: true),
    row(
      'r3',
      'ORNEK KAFE',
      8500,
      confidence: const {
        'merchant': 'MEDIUM',
        'amount': 'HIGH',
        'date': 'HIGH',
        'installment': 'HIGH',
      },
    ),
    row('r4', 'TRENDYOL.COM', 25955, credit: true, kind: BankRowKind.refund),
    row('r5', 'ESKI SATIR', 1000, duplicate: true),
  ],
  skipped: const [
    SkippedRow(
      merchant: 'Cep Şube Ödeme',
      amountMinor: 16085599,
      reason: 'PAYMENT',
    ),
    SkippedRow(
      merchant: 'TRENDYOL.COM Ödül',
      amountMinor: 2784,
      reason: 'NON_TL_AMOUNT',
    ),
  ],
);

CaptureResult _captured(String text) => CaptureResult(
  payload: CapturePayload(
    kind: CaptureKind.bankScreenshot,
    maskedText: text,
    captureDate: DateTime(2026, 11, 21),
    source: CaptureSource.gallery,
  ),
  maskedCounts: const {},
  pageCount: 1,
);

Future<TestApp> _openBank(
  WidgetTester tester, {
  BankImport? import,
  String text = 'BONUS DIJI\nGerçekleşen Hareketler\nHesap ve Kart',
  bool consent = true,
  Object? error,
  Completer<void>? gate,
}) async {
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
      if (consent) 'ai_consent': true,
    },
  );
  app.api.serverAiConsent = consent;
  app.extraction.bankResult = import ?? _garanti;
  app.extraction.bankError = error;
  app.extraction.bankGate = gate;
  app.pipeline.result = _captured(text);
  await tester.pumpWidget(app.app());
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('nav_add_button')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('add_action_/capture/bank')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('pick_image_button')));
  if (gate != null) {
    await tester.pump();
    await tester.pump();
  } else {
    await tester.pumpAndSettle();
  }
  return app;
}

final _save = find.byKey(const Key('bank_save'));

void main() {
  group('the rows', () {
    testWidgets('are listed with their badges and sections', (tester) async {
      await _openBank(tester);

      expect(find.text('Banka ekran görüntüsü'), findsOneWidget);
      expect(find.textContaining('telefonundan çıkmadı'), findsOneWidget);
      // 3 purchases, all selected by default
      expect(find.text('3 harcama okundu · 3 seçili'), findsOneWidget);
      expect(find.text('MIGROS'), findsOneWidget);
      expect(find.text('161,28 TL'), findsOneWidget);
      expect(find.text('12 Kasım 2026'), findsWidgets);
      expect(find.text('2/3'), findsOneWidget); // installment badge
      expect(find.text('Bekliyor'), findsOneWidget); // pending badge
      expect(find.text('KONTROL ET'), findsOneWidget); // merchant MEDIUM
      expect(find.text('Market'), findsOneWidget); // category chip
      // refund: kept apart, not selectable
      expect(find.text('Olası iadeler (1)'), findsOneWidget);
      expect(find.text('Olası iade'), findsOneWidget);
      expect(find.text('+259,55 TL'), findsOneWidget);
      expect(find.byKey(const Key('bank_row_check_r4')), findsNothing);
      // a duplicate: not selectable either
      expect(find.text('Daha önce eklenmiş (1)'), findsOneWidget);
      expect(find.byKey(const Key('bank_row_check_r5')), findsNothing);
      expect(find.text('Seçilenleri Kaydet (3)'), findsOneWidget);
    });

    testWidgets('the skipped rows are in a section of their own', (
      tester,
    ) async {
      await _openBank(tester);

      expect(find.text('Atlanan satırlar (2)'), findsOneWidget);
      await tester.tap(find.byKey(const Key('skipped_section')));
      await tester.pumpAndSettle();
      expect(find.text('Cep Şube Ödeme'), findsOneWidget);
      expect(find.text('Kart ödemesi'), findsOneWidget);
      expect(find.text('Puan / TL olmayan tutar'), findsOneWidget);
    });

    testWidgets('select and deselect', (tester) async {
      await _openBank(tester);

      await tester.tap(find.byKey(const Key('bank_row_check_r2')));
      await tester.pumpAndSettle();
      expect(find.text('3 harcama okundu · 2 seçili'), findsOneWidget);
      expect(find.text('Seçilenleri Kaydet (2)'), findsOneWidget);

      await tester.tap(find.byKey(const Key('bank_select_all')));
      await tester.pumpAndSettle();
      expect(find.text('3 harcama okundu · 3 seçili'), findsOneWidget);

      await tester.tap(find.byKey(const Key('bank_select_all')));
      await tester.pumpAndSettle();
      expect(find.text('3 harcama okundu · 0 seçili'), findsOneWidget);
      expect(tester.widget<FilledButton>(_save).onPressed, isNull);
    });

    testWidgets('a screenshot without purchases says so', (tester) async {
      await _openBank(
        tester,
        import: const BankImport(bankKey: null, rows: [], skipped: []),
      );
      expect(find.text('Harcama satırı bulunamadı'), findsOneWidget);
    });

    testWidgets('a screenshot of only known rows says they are known', (
      tester,
    ) async {
      await _openBank(
        tester,
        import: BankImport(
          bankKey: BankKey.garanti,
          rows: [row('d1', 'ESKI SATIR', 1000, duplicate: true)],
          skipped: const [],
        ),
      );
      expect(find.text('Yeni harcama yok'), findsOneWidget);
      expect(find.text('Harcama satırı bulunamadı'), findsNothing);
      expect(find.text('Daha önce eklenmiş (1)'), findsOneWidget);
    });
  });

  group('the bank', () {
    testWidgets('is guessed from the text and sent as the hint', (
      tester,
    ) async {
      final app = await _openBank(tester);

      expect(app.extraction.bankCalls.single.bankHint, 'garanti');
      expect(find.text('Garanti BBVA'), findsOneWidget);
    });

    testWidgets('an unknown bank is sent without a hint', (tester) async {
      final app = await _openBank(
        tester,
        text: 'DÖNEM İÇİ HAREKETLER\n0 ParaPuan\nHesap Kesim Tarihi',
        import: const BankImport(bankKey: null, rows: [], skipped: []),
      );

      expect(app.extraction.bankCalls.single.bankHint, isNull);
      expect(find.text('Diğer banka'), findsOneWidget);
    });

    testWidgets(
      'can be changed: the old rows are dropped and the text is read again',
      (tester) async {
        final app = await _openBank(tester);

        await tester.tap(find.byKey(const Key('bank_chip')));
        await tester.pumpAndSettle();
        await tester.tap(find.byKey(const Key('bank_option_kuveyt')));
        await tester.pumpAndSettle();

        expect(app.extraction.bankCalls.map((c) => c.bankHint), [
          'garanti',
          'kuveyt',
        ]);
        // the rows of the first reading were rejected on the server (not the duplicate)
        expect(app.transactions.rejected, ['r1', 'r2', 'r3', 'r4']);
        expect(find.text('Kuveyt Türk'), findsOneWidget);
      },
    );

    testWidgets('"Diğer banka" reads without help', (tester) async {
      final app = await _openBank(tester);

      await tester.tap(find.byKey(const Key('bank_chip')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('bank_option_other')));
      await tester.pumpAndSettle();

      expect(app.extraction.bankCalls.last.bankHint, isNull);
    });
  });

  group('editing', () {
    testWidgets('a corrected row is sent with its changes', (tester) async {
      final app = await _openBank(tester);

      await tester.tap(find.byKey(const Key('bank_row_edit_r3')));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const Key('bank_edit_merchant')),
        'Kafe Nero',
      );
      await tester.enterText(
        find.byKey(const Key('bank_edit_amount')),
        '92,50',
      );
      await tester.tap(find.byKey(const Key('bank_edit_category')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('category_FOOD_DRINK')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('bank_edit_save')));
      await tester.pumpAndSettle();

      expect(find.text('Kafe Nero'), findsOneWidget);
      expect(find.text('92,50 TL'), findsOneWidget);

      await tester.tap(_save);
      await tester.pumpAndSettle();

      final edit = app.transactions.batches.single.edits['r3']!;
      expect(edit.merchant, 'Kafe Nero');
      expect(edit.amountMinor, 9250);
      expect(edit.category, SpendingCategory.foodDrink);
    });

    testWidgets('the edit sheet needs a merchant and an amount', (
      tester,
    ) async {
      await _openBank(tester);
      await tester.tap(find.byKey(const Key('bank_row_edit_r1')));
      await tester.pumpAndSettle();

      await tester.enterText(find.byKey(const Key('bank_edit_merchant')), '  ');
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('bank_edit_save')))
            .onPressed,
        isNull,
      );
    });
  });

  group('saving', () {
    testWidgets('sends the selected rows and discards the others', (
      tester,
    ) async {
      final app = await _openBank(tester);
      await tester.tap(
        find.byKey(const Key('bank_row_check_r2')),
      ); // deselect one

      await tester.tap(_save);
      await tester.pumpAndSettle();

      expect(app.transactions.batches.single.ids, ['r1', 'r3']);
      expect(app.transactions.rejected, ['r2']); // what was left out
      // lands on the purchase list with a message
      expect(find.text('2 harcama kaydedildi.'), findsOneWidget);
      expect(find.text('Harcamalar'), findsWidgets);
    });

    testWidgets('a row the server could not save is reported', (tester) async {
      final app = await _openBank(tester);
      app.transactions.batchResult = const BatchResult(
        created: 0,
        skipped: {'r3': 'MISSING_DATE'},
      );

      await tester.tap(_save);
      await tester.pumpAndSettle();

      expect(
        find.text('2 harcama kaydedildi, 1 satır kaydedilemedi.'),
        findsOneWidget,
      );
    });

    testWidgets('a server error is shown and the rows stay', (tester) async {
      final app = await _openBank(tester);
      app.transactions.writeError = fakeApiError('NETWORK_UNREACHABLE');

      await tester.tap(_save);
      await tester.pumpAndSettle();

      expect(find.text('Banka ekran görüntüsü'), findsOneWidget);
      expect(find.text(messageForCode('NETWORK_UNREACHABLE')), findsOneWidget);
      expect(app.transactions.batches, isEmpty);

      await tester.tap(_save);
      await tester.pumpAndSettle();
      expect(app.transactions.batches, hasLength(1));
    });

    testWidgets('a row without a date blocks saving until it is deselected', (
      tester,
    ) async {
      await _openBank(
        tester,
        import: BankImport(
          bankKey: BankKey.akbank,
          rows: [
            row('a1', 'ORNEK IFFCO', 882668, seq: 4, count: 4, noDate: true),
          ],
          skipped: const [],
        ),
      );

      expect(find.text('Tarih okunamadı'), findsOneWidget);
      expect(find.byKey(const Key('bank_missing_date')), findsOneWidget);
      expect(tester.widget<FilledButton>(_save).onPressed, isNull);

      await tester.tap(find.byKey(const Key('bank_row_check_a1')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('bank_missing_date')), findsNothing);
    });

    testWidgets('no image is kept or uploaded for a bank screenshot', (
      tester,
    ) async {
      final app = await _openBank(tester);
      await tester.tap(_save);
      await tester.pumpAndSettle();

      expect(app.documents.uploads, isEmpty);
      expect(app.pipeline.inputs.single.keepImage, isFalse);
    });
  });

  group('leaving', () {
    testWidgets('Vazgeç asks, then rejects every row of the screenshot', (
      tester,
    ) async {
      final app = await _openBank(tester);

      await tester.tap(find.byKey(const Key('bank_cancel')));
      await tester.pumpAndSettle();
      expect(find.text('Kaydetmeden çıkılsın mı?'), findsOneWidget);
      await tester.tap(find.byKey(const Key('leave_confirm')));
      await tester.pumpAndSettle();

      expect(app.transactions.rejected, ['r1', 'r2', 'r3', 'r4']);
      expect(app.transactions.batches, isEmpty);
      expect(find.text('Banka ekran görüntüsü'), findsNothing);
    });

    testWidgets('"Devam et" changes nothing', (tester) async {
      final app = await _openBank(tester);
      await tester.tap(find.byKey(const Key('bank_cancel')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('leave_stay')));
      await tester.pumpAndSettle();

      expect(find.text('Banka ekran görüntüsü'), findsOneWidget);
      expect(app.transactions.rejected, isEmpty);
    });
  });

  group('when it can not be read', () {
    testWidgets('the AI switch is off', (tester) async {
      final app = await _openBank(tester, consent: false);

      expect(find.text('Okunamadı'), findsOneWidget);
      expect(
        find.textContaining('Yapay zekâ ile okuma kapalı'),
        findsOneWidget,
      );
      expect(find.text("Ayarlar'a git"), findsOneWidget);
      expect(app.extraction.bankCalls.length, 1);
    });

    testWidgets('a current-account screen is refused with an explanation', (
      tester,
    ) async {
      await _openBank(tester, error: fakeApiError('BANK_SCREEN_NOT_SUPPORTED'));

      expect(find.text('Bu ekran kart hareketi değil'), findsOneWidget);
      expect(find.text('Başka ekran seç'), findsOneWidget);
    });

    testWidgets('a server problem can be retried', (tester) async {
      final app = await _openBank(
        tester,
        error: fakeApiError('EXTRACTION_FAILED'),
      );
      expect(find.text('Tekrar dene'), findsOneWidget);

      app.extraction.bankError = null;
      await tester.tap(find.text('Tekrar dene'));
      await tester.pumpAndSettle();

      expect(find.text('3 harcama okundu · 3 seçili'), findsOneWidget);
      expect(app.extraction.bankCalls, hasLength(2));
    });

    testWidgets('the reading state can be cancelled', (tester) async {
      final gate = Completer<void>();
      final app = await _openBank(tester, gate: gate);

      expect(find.textContaining('Satırlar okunuyor'), findsOneWidget);
      await tester.tap(find.byKey(const Key('bank_extract_cancel')));
      await tester.pumpAndSettle();

      expect(find.text('Banka ekran görüntüsü'), findsNothing);
      expect(app.transactions.batches, isEmpty);
      gate.complete();
      await tester.pumpAndSettle();
    });
  });

  test('the bank import code has no way to upload an image (spec 15.3)', () {
    final files = Directory('lib/features/capture/presentation/bank')
        .listSync()
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart') && !f.path.endsWith('.g.dart'));
    expect(files, isNotEmpty);
    for (final file in files) {
      final source = file.readAsStringSync();
      expect(source, isNot(contains('documents_api')), reason: file.path);
      expect(source, isNot(contains('DocumentsApi')), reason: file.path);
      expect(source, isNot(contains('.upload(')), reason: file.path);
      expect(source, isNot(contains('retainedImage')), reason: file.path);
    }
  });
}
