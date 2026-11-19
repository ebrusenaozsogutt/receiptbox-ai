import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/core/networking/api_error.dart';
import 'package:receiptbox/core/privacy/pii_masker.dart';
import 'package:receiptbox/features/capture/data/extraction_api.dart';
import 'package:receiptbox/features/capture/domain/capture_payload.dart';
import 'package:receiptbox/features/capture/domain/extraction_result.dart';
import 'package:receiptbox/features/transactions/domain/spending_category.dart';

import '../../support/fakes.dart';
import '../../support/purchase_fakes.dart';

ExtractionResult _extraction({
  Map<String, String> confidence = const {
    'merchant': 'HIGH',
    'date': 'HIGH',
    'time': 'HIGH',
    'total': 'HIGH',
    'items': 'HIGH',
  },
  List<ExtractedLine> lines = const [
    ExtractedLine(name: 'SUT 1L', totalMinor: 10000),
    ExtractedLine(name: 'EKMEK', totalMinor: 17030),
  ],
  String categorySource = 'MERCHANT_DEFAULT',
}) => ExtractionResult(
  observationId: 'obs-1',
  merchant: 'MIGROS TICARET A.S.',
  date: '2026-11-14',
  total: '270.30',
  itemCount: lines.length,
  confidence: confidence,
  merchantMatch: 'GLOBAL_ALIAS',
  merchantName: 'Migros',
  categoryKey: 'GROCERY',
  categorySource: categorySource,
  aiUsed: true,
  usedQr: false,
  time: '18:42:00',
  totalMinor: 27030,
  lines: lines,
);

CaptureResult _captured({File? kept}) => CaptureResult(
  payload: CapturePayload(
    kind: CaptureKind.receipt,
    maskedText: 'MIGROS\nTOPLAM 270,30',
    captureDate: DateTime(2026, 11, 14),
    source: CaptureSource.gallery,
  ),
  maskedCounts: const {PiiType.phone: 1},
  pageCount: 1,
  retainedImage: kept,
);

Future<TestApp> _openReview(
  WidgetTester tester, {
  ExtractionResult? extraction,
  CaptureResult? captured,
  bool consent = true,
  Object? extractionError,
  Completer<void>? extractionGate,
}) async {
  // A tall screen, so that the whole form is built and visible at once.
  tester.view.physicalSize = const Size(800, 2000);
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
  app.extraction.result = extraction ?? _extraction();
  app.extraction.error = extractionError;
  app.extraction.gate = extractionGate;
  app.pipeline.result = captured ?? _captured();
  await tester.pumpWidget(app.app());
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('nav_add_button')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('add_action_/capture/gallery')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('pick_image_button')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(const Key('kind_receipt')));
  if (extractionGate != null) {
    // The progress indicator never stops animating: settle is not possible.
    await tester.pump();
    await tester.pump();
  } else {
    await tester.pumpAndSettle();
  }
  return app;
}

Future<void> _show(WidgetTester tester, Finder finder) async {
  await tester.dragUntilVisible(
    finder,
    find.byType(ListView).first,
    const Offset(0, -200),
  );
  await tester.pumpAndSettle();
}

final _save = find.byKey(const Key('review_save'));
final _cancel = find.byKey(const Key('review_cancel'));

void main() {
  group('what the screen shows', () {
    testWidgets('a clearly read receipt: every field is checked, no warnings', (
      tester,
    ) async {
      await _openReview(tester);

      expect(find.text('Fişi kontrol et'), findsOneWidget);
      expect(find.text('Yanlış olan alanı düzeltip kaydet'), findsOneWidget);
      expect(find.text('Tüm alanlar fişte doğrulandı.'), findsOneWidget);
      expect(find.text('KONTROL ET'), findsNothing);
      for (final key in [
        'check_merchant',
        'check_date',
        'check_time',
        'check_total',
      ]) {
        expect(find.byKey(Key(key)), findsOneWidget, reason: key);
      }
      expect(find.text('Migros'), findsOneWidget);
      expect(find.text('14 Kasım 2026'), findsOneWidget);
      expect(find.text('18:42'), findsOneWidget);
      expect(find.text('Market'), findsOneWidget);
      expect(find.text('Mağazada'), findsOneWidget);
      expect(find.text('Online'), findsOneWidget);
      expect(find.text('Kalemler (2)'), findsOneWidget);
      expect(
        tester.widget<TextField>(find.descendant(
          of: find.byKey(const Key('field_total')),
          matching: find.byType(TextField),
        )).controller!.text,
        '270,30',
      );
    });

    testWidgets('MEDIUM and LOW fields get the KONTROL ET badge and are counted', (
      tester,
    ) async {
      await _openReview(
        tester,
        extraction: _extraction(
          confidence: const {
            'merchant': 'MEDIUM',
            'date': 'HIGH',
            'time': 'HIGH',
            'total': 'LOW',
            'items': 'HIGH',
          },
        ),
      );

      expect(
        find.text('2 alan kontrol bekliyor. Diğerleri fişte doğrulandı.'),
        findsOneWidget,
      );
      expect(find.text('KONTROL ET'), findsNWidgets(2));
      expect(find.byKey(const Key('check_merchant')), findsNothing);
      expect(find.byKey(const Key('check_total')), findsNothing);
      expect(find.byKey(const Key('check_date')), findsOneWidget);
    });

    testWidgets('editing a flagged field clears its flag', (tester) async {
      await _openReview(
        tester,
        extraction: _extraction(
          confidence: const {
            'merchant': 'MEDIUM',
            'date': 'HIGH',
            'time': 'HIGH',
            'total': 'LOW',
            'items': 'HIGH',
          },
        ),
      );

      await tester.enterText(find.byKey(const Key('field_merchant')), 'Migros Jet');
      await tester.pumpAndSettle();

      expect(
        find.text('1 alan kontrol bekliyor. Diğerleri fişte doğrulandı.'),
        findsOneWidget,
      );
      expect(find.text('KONTROL ET'), findsOneWidget);
      expect(find.byKey(const Key('check_merchant')), findsOneWidget);

      await tester.enterText(find.byKey(const Key('field_total')), '270,35');
      await tester.pumpAndSettle();
      expect(find.text('Tüm alanlar fişte doğrulandı.'), findsOneWidget);
      expect(find.text('KONTROL ET'), findsNothing);
    });

    testWidgets('the items card says whether the lines add up to the total', (
      tester,
    ) async {
      await _openReview(tester);
      await _show(tester, find.byKey(const Key('items_sum_check')));
      expect(
        find.text('Kalemlerin toplamı fiş toplamıyla uyuşuyor'),
        findsOneWidget,
      );

      // Now the total is changed: the lines no longer add up.
      await tester.dragUntilVisible(
        find.byKey(const Key('field_total')),
        find.byType(ListView).first,
        const Offset(0, 200),
      );
      await tester.enterText(find.byKey(const Key('field_total')), '300,00');
      await tester.pumpAndSettle();
      await _show(tester, find.byKey(const Key('items_sum_check')));
      expect(
        find.textContaining('Kalemlerin toplamı fiş toplamıyla uyuşmuyor'),
        findsOneWidget,
      );
      expect(find.textContaining('29,70 TL fark'), findsOneWidget);
    });

    testWidgets('the channel can be switched', (tester) async {
      final app = await _openReview(tester);
      await tester.tap(find.text('Online'));
      await tester.pumpAndSettle();
      await tester.tap(_save);
      await tester.pumpAndSettle();

      expect(app.transactions.confirmed.single.input.channel.key, 'ONLINE');
    });
  });

  group('saving', () {
    testWidgets('confirms the observation with what the screen shows', (
      tester,
    ) async {
      final app = await _openReview(tester);
      await tester.enterText(find.byKey(const Key('field_merchant')), 'Migros Jet');
      await tester.pumpAndSettle();

      await tester.tap(_save);
      await tester.pumpAndSettle();

      final call = app.transactions.confirmed.single;
      expect(call.observationId, 'obs-1');
      expect(call.input.merchant, 'Migros Jet');
      expect(call.input.totalMinor, 27030);
      expect(call.input.date, DateTime(2026, 11, 14));
      expect(call.input.time, const TimeOfDay(hour: 18, minute: 42));
      expect(call.input.category, SpendingCategory.grocery);
      expect(call.input.rememberCategory, isFalse);
      expect(call.input.lines.map((l) => l.name), ['SUT 1L', 'EKMEK']);
      expect(call.input.lines.map((l) => l.totalMinor), [10000, 17030]);

      // The user lands on the purchase list, where the new purchase is.
      expect(find.text('Harcama kaydedildi.'), findsOneWidget);
      expect(find.text('Harcamalar'), findsWidgets);
      expect(find.text('Migros Jet'), findsOneWidget);
    });

    testWidgets('an unchanged category does not ask "hep böyle olsun mu?"', (
      tester,
    ) async {
      await _openReview(tester);
      await tester.tap(_save);
      await tester.pumpAndSettle();

      expect(find.text('Bu mağaza için hep böyle olsun mu?'), findsNothing);
    });

    testWidgets('a changed category asks first; "Evet" is sent with the request', (
      tester,
    ) async {
      final app = await _openReview(tester);
      await tester.tap(find.byKey(const Key('field_category')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('category_FOOD_DRINK')));
      await tester.pumpAndSettle();
      expect(find.text('Yeme-İçme'), findsOneWidget);

      await tester.tap(_save);
      await tester.pumpAndSettle();
      expect(find.text('Bu mağaza için hep böyle olsun mu?'), findsOneWidget);
      expect(app.transactions.confirmed, isEmpty); // asked BEFORE saving

      await tester.tap(find.byKey(const Key('remember_yes')));
      await tester.pumpAndSettle();

      final input = app.transactions.confirmed.single.input;
      expect(input.category, SpendingCategory.foodDrink);
      expect(input.rememberCategory, isTrue);
    });

    testWidgets('"Sadece bu sefer" saves without the rule', (tester) async {
      final app = await _openReview(tester);
      await tester.tap(find.byKey(const Key('field_category')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('category_FOOD_DRINK')));
      await tester.pumpAndSettle();
      await tester.tap(_save);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('remember_no')));
      await tester.pumpAndSettle();

      expect(app.transactions.confirmed.single.input.rememberCategory, isFalse);
    });

    testWidgets('a server error is shown and the form stays', (tester) async {
      final app = await _openReview(tester);
      app.transactions.writeError = fakeApiError('NETWORK_UNREACHABLE');

      await tester.tap(_save);
      await tester.pumpAndSettle();

      expect(find.text('Fişi kontrol et'), findsOneWidget);
      expect(find.text(messageForCode('NETWORK_UNREACHABLE')), findsOneWidget);
      expect(app.transactions.confirmed, isEmpty);

      // And trying again works.
      await tester.tap(_save);
      await tester.pumpAndSettle();
      expect(app.transactions.confirmed, hasLength(1));
    });

    testWidgets('the button is disabled while saving and cannot be pressed twice', (
      tester,
    ) async {
      final app = await _openReview(tester);
      app.transactions.confirmGate = Completer<void>();

      await tester.tap(_save);
      await tester.pump();
      await tester.pump();
      expect(tester.widget<FilledButton>(_save).onPressed, isNull);

      app.transactions.confirmGate!.complete();
      await tester.pumpAndSettle();
      expect(app.transactions.confirmed, hasLength(1));
    });

    testWidgets('a total of zero cannot be saved', (tester) async {
      await _openReview(tester);
      await tester.enterText(find.byKey(const Key('field_total')), '0');
      await tester.pumpAndSettle();
      expect(tester.widget<FilledButton>(_save).onPressed, isNull);
    });
  });

  group('leaving', () {
    testWidgets('Vazgeç asks, then rejects the receipt on the server', (
      tester,
    ) async {
      final app = await _openReview(tester);

      await tester.tap(_cancel);
      await tester.pumpAndSettle();
      expect(find.text('Kaydetmeden çıkılsın mı?'), findsOneWidget);

      await tester.tap(find.byKey(const Key('leave_confirm')));
      await tester.pumpAndSettle();

      expect(app.transactions.rejected, ['obs-1']);
      expect(app.transactions.confirmed, isEmpty);
      expect(find.text('Fişi kontrol et'), findsNothing);
    });

    testWidgets('"Devam et" stays on the screen and changes nothing', (
      tester,
    ) async {
      final app = await _openReview(tester);
      await tester.tap(_cancel);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('leave_stay')));
      await tester.pumpAndSettle();

      expect(find.text('Fişi kontrol et'), findsOneWidget);
      expect(app.transactions.rejected, isEmpty);
    });

    testWidgets('the back arrow asks the same question', (tester) async {
      await _openReview(tester);
      await tester.tap(find.byKey(const Key('review_back')));
      await tester.pumpAndSettle();
      expect(find.text('Kaydetmeden çıkılsın mı?'), findsOneWidget);
    });
  });

  group('when the receipt could not be read', () {
    testWidgets('shows the reading state and can be cancelled', (tester) async {
      final gate = Completer<void>();
      final app = await _openReview(tester, extractionGate: gate);

      expect(find.textContaining('Fiş okunuyor'), findsOneWidget);
      await tester.tap(find.byKey(const Key('review_extract_cancel')));
      await tester.pumpAndSettle();

      expect(find.text('Fişi kontrol et'), findsNothing);
      expect(app.transactions.confirmed, isEmpty);
      gate.complete();
      await tester.pumpAndSettle();
    });

    for (final entry in {
      'EXTRACTION_FAILED': 'Fiş şu an okunamadı',
      'EXTRACTION_REJECTED': 'Fiş güvenilir okunamadı',
      'QR_INVALID': 'QR kodu okunamadı',
    }.entries) {
      testWidgets('${entry.key} opens an empty form with a notice', (
        tester,
      ) async {
        final app = await _openReview(
          tester,
          extractionError: fakeApiError(entry.key),
        );

        expect(find.textContaining(entry.value), findsOneWidget);
        // The form is empty: saving is not possible until merchant and total are filled in.
        expect(tester.widget<FilledButton>(_save).onPressed, isNull);

        await tester.enterText(find.byKey(const Key('field_merchant')), 'Kırtasiye');
        await tester.enterText(find.byKey(const Key('field_total')), '45,50');
        await tester.pumpAndSettle();
        await tester.tap(_save);
        await tester.pumpAndSettle();

        // No observation exists, so it is saved as a manual purchase.
        expect(app.transactions.confirmed, isEmpty);
        final input = app.transactions.created.single;
        expect(input.merchant, 'Kırtasiye');
        expect(input.totalMinor, 4550);
      });
    }

    testWidgets('AI reading switched off also opens the manual form', (
      tester,
    ) async {
      final app = await _openReview(
        tester,
        consent: false,
        extractionError: const AiConsentOffException(),
      );

      expect(find.textContaining('Yapay zekâ ile okuma kapalı'), findsOneWidget);
      await tester.enterText(find.byKey(const Key('field_merchant')), 'Bakkal');
      await tester.enterText(find.byKey(const Key('field_total')), '12');
      await tester.pumpAndSettle();
      await tester.tap(_save);
      await tester.pumpAndSettle();

      expect(app.transactions.created.single.totalMinor, 1200);
    });

    testWidgets('Vazgeç on a manual form rejects nothing', (tester) async {
      final app = await _openReview(
        tester,
        extractionError: fakeApiError('EXTRACTION_FAILED'),
      );
      await tester.tap(_cancel);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('leave_confirm')));
      await tester.pumpAndSettle();

      expect(app.transactions.rejected, isEmpty);
    });
  });
}
