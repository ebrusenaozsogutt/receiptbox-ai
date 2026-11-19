import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/app.dart';
import 'package:receiptbox/features/capture/data/capture_providers.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/core/privacy/pii_masker.dart';
import 'package:receiptbox/features/capture/data/extraction_api.dart';
import 'package:receiptbox/features/capture/domain/capture_payload.dart';
import 'package:receiptbox/features/capture/domain/extraction_result.dart';

import '../../support/fakes.dart';

CaptureResult _captured({
  Map<String, dynamic>? qr,
  CaptureKind kind = CaptureKind.receipt,
}) => CaptureResult(
  payload: CapturePayload(
    kind: kind,
    maskedText: 'ORNEK ELEKTRONIK\nTOPLAM 2.499,00',
    qrPayload: qr,
    captureDate: DateTime(2026, 11, 18),
    source: CaptureSource.gallery,
  ),
  maskedCounts: const {PiiType.name: 1},
  pageCount: 1,
);

Future<TestApp> _openResult(
  WidgetTester tester, {
  required CaptureResult captured,
  bool consent = true,
}) async {
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
  app.pipeline.result = captured;
  await tester.pumpWidget(app.app());
  await tester.pumpAndSettle();
  // Since P07 a receipt goes to the review screen; the debug "Okunan bilgiler" screen (with the
  // server panel) is opened the way the debug link does it.
  final container = ProviderScope.containerOf(
    tester.element(find.byType(MaterialApp)),
  );
  container.read(captureFlowProvider.notifier).showForDebug(captured);
  unawaited(container.read(routerProvider).push('/capture/result'));
  await tester.pumpAndSettle();
  return app;
}

final _send = find.byKey(const Key('send_to_server_button'));

Future<void> _show(WidgetTester tester, Finder finder) async {
  await tester.dragUntilVisible(
    finder,
    find.byType(ListView),
    const Offset(0, -300),
  );
  await tester.pumpAndSettle();
}

Future<void> _tapSend(WidgetTester tester) async {
  await _show(tester, _send);
  await tester.tap(_send);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('a receipt: the button sends it and the answer is shown', (
    tester,
  ) async {
    final app = await _openResult(tester, captured: _captured());

    expect(find.text('Sunucu (yalnızca debug)'), findsOneWidget);
    expect(find.textContaining('orijinal metin gönderilmez'), findsOneWidget);
    await _tapSend(tester);

    final call = app.extraction.calls.single;
    expect(call.payload.maskedText, contains('TOPLAM'));
    expect(call.aiConsent, isTrue);
    final card = find.byKey(const Key('server_result'));
    expect(card, findsOneWidget);
    expect(
      find.descendant(of: card, matching: find.text('Toplam: 270.30 TL')),
      findsOneWidget,
    );
    expect(
      find.text('İşyeri önerisi: Migros (bilinen işyeri)'),
      findsOneWidget,
    );
    expect(
      find.text('Kategori önerisi: Market (işyerinin varsayılanı)'),
      findsOneWidget,
    );
    expect(find.textContaining('Kalemler: LOW'), findsOneWidget);
    expect(find.text('Kaynak: fiş metni (yapay zekâ)'), findsOneWidget);
  });

  testWidgets('nothing is sent until the button is pressed', (tester) async {
    final app = await _openResult(tester, captured: _captured());

    expect(app.extraction.calls, isEmpty);
  });

  testWidgets(
    'while it is sending the button says so and cannot be pressed again',
    (tester) async {
      final app = await _openResult(tester, captured: _captured());
      app.extraction.gate = Completer<void>();
      await tester.ensureVisible(_send);
      await tester.pumpAndSettle();

      await tester.tap(_send);
      await tester.pump();

      expect(find.text('Gönderiliyor…'), findsOneWidget);
      expect(tester.widget<OutlinedButton>(_send).onPressed, isNull);
      app.extraction.gate!.complete();
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('server_result')), findsOneWidget);
    },
  );

  testWidgets(
    'without the AI consent a receipt text is not sent and Settings is suggested',
    (tester) async {
      final app = await _openResult(
        tester,
        captured: _captured(),
        consent: false,
      );
      app.extraction.error = const AiConsentOffException();

      await _tapSend(tester);

      expect(
        find.textContaining('Yapay zekâ ile okuma kapalı'),
        findsOneWidget,
      );
      expect(find.byKey(const Key('server_result')), findsNothing);
      expect(app.extraction.calls.single.aiConsent, isFalse);
    },
  );

  testWidgets('a GİB QR shows the QR source and says the AI was not used', (
    tester,
  ) async {
    final app = await _openResult(
      tester,
      captured: _captured(qr: const {'ettn': 'x', 'odenecek': '2499.00'}),
      consent: false,
    );
    app.extraction.result = ExtractionResult.fromJson({
      'observation_id': 'obs-2',
      'extraction': {
        'merchant_raw': null,
        'date': '2026-11-14',
        'total': '2499.00',
        'items': <dynamic>[],
      },
      'confidence': {'total': 'HIGH', 'date': 'HIGH', 'merchant': 'LOW'},
      'suggestions': {
        'merchant': {
          'match': 'NONE',
          'merchant_id': null,
          'canonical_name': null,
        },
        'category': {'key': 'OTHER', 'source': 'FALLBACK'},
      },
      'ai_used': false,
    }, usedQr: true);

    expect(find.textContaining('e-Fatura QR bilgisini'), findsOneWidget);
    await _tapSend(tester);

    expect(app.extraction.calls.single.payload.qrPayload, isNotNull);
    expect(
      find.text('Kaynak: e-Fatura QR (yapay zekâ kullanılmadı)'),
      findsOneWidget,
    );
    expect(find.text('Toplam: 2499.00 TL'), findsOneWidget);
    expect(find.text('İşyeri önerisi: — (işyeri adı yok)'), findsOneWidget);
    expect(find.text('Kategori önerisi: Diğer (tahmin yok)'), findsOneWidget);
  });

  for (final entry in {
    'EXTRACTION_FAILED': 'yapay zekâ servisi yanıt vermedi',
    'EXTRACTION_REJECTED': 'tutar mantıksız',
    'QR_INVALID': 'QR kodu okunabilir',
    'TEXT_TOO_LARGE': 'en fazla 20 KB',
    'AI_CONSENT_REQUIRED': 'Yapay zekâ ile okuma kapalı',
    'RATE_LIMITED': 'Çok fazla deneme',
  }.entries) {
    testWidgets('error ${entry.key} gives a Turkish message', (tester) async {
      final app = await _openResult(tester, captured: _captured());
      app.extraction.error = apiError(entry.key, status: 422);

      await _tapSend(tester);

      expect(find.textContaining(entry.value), findsOneWidget);
    });
  }

  testWidgets('a bank screenshot has no server button yet (P08)', (
    tester,
  ) async {
    await _openResult(
      tester,
      captured: _captured(kind: CaptureKind.bankScreenshot),
    );

    expect(_send, findsNothing);
    expect(find.text('Sunucu (yalnızca debug)'), findsNothing);
  });
}
