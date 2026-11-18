import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/core/privacy/pii_masker.dart';
import 'package:receiptbox/features/capture/data/capture_providers.dart';
import 'package:receiptbox/features/capture/data/media_sources.dart';
import 'package:receiptbox/features/capture/domain/capture_payload.dart';

import '../../support/fakes.dart';

Future<TestApp> _openApp(
  WidgetTester tester, {
  List<SharedFile> shared = const [],
  Future<List<CameraDescription>> Function()? cameras,
}) async {
  final app = await TestApp.signedIn();
  app.sharedMedia.initialFiles = shared;
  if (cameras != null) app.cameras = cameras;
  await tester.pumpWidget(app.app());
  await tester.pumpAndSettle();
  return app;
}

Future<void> _openAddAction(WidgetTester tester, String route) async {
  await tester.tap(find.byKey(const Key('nav_add_button')));
  await tester.pumpAndSettle();
  await tester.tap(find.byKey(Key('add_action_$route')));
  await tester.pumpAndSettle();
}

void main() {
  group('gallery', () {
    testWidgets('pick -> ask the kind -> read -> masked result', (
      tester,
    ) async {
      final app = await _openApp(tester);
      await _openAddAction(tester, '/capture/gallery');

      expect(find.text('Fotoğraf seç'), findsOneWidget);
      await tester.tap(find.byKey(const Key('pick_image_button')));
      await tester.pumpAndSettle();

      expect(find.text('Bu bir ne?'), findsOneWidget);
      await tester.tap(find.byKey(const Key('kind_receipt')));
      await tester.pumpAndSettle();

      final input = app.pipeline.inputs.single;
      expect(input.kind, CaptureKind.receipt);
      expect(input.source, CaptureSource.gallery);
      expect(input.captureDate, DateTime(2026, 11, 1));
      expect(input.isPdf, isFalse);

      expect(find.text('Okunan bilgiler'), findsOneWidget);
      expect(find.text('1 hassas bilgi gizlendi: 1 telefon.'), findsOneWidget);
      final masked = tester.widget<Text>(
        find.descendant(
          of: find.byKey(const Key('masked_text')),
          matching: find.byType(Text),
        ),
      );
      expect(masked.data, contains('[PHONE]'));
      expect(masked.data, isNot(contains('0532')));
      // Debug build: the original is shown next to it, with a warning.
      expect(find.text('Orijinal metin (yalnızca debug)'), findsOneWidget);
      expect(find.textContaining('hiçbir yere gönderilmedi'), findsOneWidget);
    });

    testWidgets('closing the kind sheet reads nothing', (tester) async {
      final app = await _openApp(tester);
      await _openAddAction(tester, '/capture/gallery');
      await tester.tap(find.byKey(const Key('pick_image_button')));
      await tester.pumpAndSettle();

      await tester.tapAt(
        const Offset(5, 5),
      ); // the dimmed area closes the sheet
      await tester.pumpAndSettle();

      expect(app.pipeline.inputs, isEmpty);
      expect(find.text('Galeriden Ekle'), findsWidgets);
      expect(find.byKey(const Key('pick_image_button')), findsOneWidget);
    });

    testWidgets('cancelling the picker changes nothing', (tester) async {
      final app = await _openApp(tester);
      app.gallery.next = null;
      await _openAddAction(tester, '/capture/gallery');

      await tester.tap(find.byKey(const Key('pick_image_button')));
      await tester.pumpAndSettle();

      expect(app.gallery.calls, 1);
      expect(find.text('Bu bir ne?'), findsNothing);
      expect(app.pipeline.inputs, isEmpty);
    });

    testWidgets('a picker error shows a message and allows another try', (
      tester,
    ) async {
      final app = await _openApp(tester);
      app.gallery.error = StateError('boom');
      await _openAddAction(tester, '/capture/gallery');

      await tester.tap(find.byKey(const Key('pick_image_button')));
      await tester.pumpAndSettle();

      expect(find.text('Galeri açılamadı. Tekrar dene.'), findsOneWidget);
      expect(find.textContaining('boom'), findsNothing);
      final button = tester.widget<FilledButton>(
        find.byKey(const Key('pick_image_button')),
      );
      expect(button.onPressed, isNotNull);
    });
  });

  group('bank screenshot', () {
    testWidgets('does not ask the kind and says the image stays on the phone', (
      tester,
    ) async {
      final app = await _openApp(tester);
      await _openAddAction(tester, '/capture/bank');

      expect(find.textContaining('telefonundan çıkmaz'), findsOneWidget);
      await tester.tap(find.byKey(const Key('pick_image_button')));
      await tester.pumpAndSettle();

      expect(find.text('Bu bir ne?'), findsNothing);
      expect(app.pipeline.inputs.single.kind, CaptureKind.bankScreenshot);
      expect(find.text('Okunan bilgiler'), findsOneWidget);
    });
  });

  group('result screen', () {
    testWidgets('shows the reading state while the pipeline works', (
      tester,
    ) async {
      final app = await _openApp(tester);
      app.pipeline.gate = Completer<void>();
      await _openAddAction(tester, '/capture/bank');

      await tester.tap(find.byKey(const Key('pick_image_button')));
      await tester.pump();
      await tester.pump();

      expect(find.text('Yazı telefonunda okunuyor…'), findsOneWidget);

      app.pipeline.gate!.complete();
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('masked_text')), findsOneWidget);
    });

    testWidgets(
      'a failure shows the Turkish message and "Tekrar dene" goes back',
      (tester) async {
        final app = await _openApp(tester);
        app.pipeline.error = const CaptureException(CaptureFailure.noTextFound);
        await _openAddAction(tester, '/capture/bank');
        await tester.tap(find.byKey(const Key('pick_image_button')));
        await tester.pumpAndSettle();

        expect(find.text('Okunamadı'), findsOneWidget);
        expect(
          find.textContaining('okunabilir yazı bulunamadı'),
          findsOneWidget,
        );

        await tester.tap(find.text('Tekrar dene'));
        await tester.pumpAndSettle();
        expect(find.text('Banka Ekran Görüntüsü'), findsWidgets);
        expect(find.byKey(const Key('pick_image_button')), findsOneWidget);
      },
    );

    testWidgets('a GİB QR code and several masked kinds are summarised', (
      tester,
    ) async {
      final app = await _openApp(tester);
      app.pipeline.result = CaptureResult(
        payload: CapturePayload(
          kind: CaptureKind.receipt,
          maskedText: 'x',
          qrPayload: const {'ettn': 'abc'},
          captureDate: DateTime(2026, 11, 18),
          source: CaptureSource.gallery,
        ),
        maskedCounts: const {PiiType.iban: 2, PiiType.email: 1},
        pageCount: 2,
      );
      await _openAddAction(tester, '/capture/bank');
      await tester.tap(find.byKey(const Key('pick_image_button')));
      await tester.pumpAndSettle();

      expect(find.textContaining('e-Fatura QR kodu bulundu'), findsOneWidget);
      expect(
        find.text('3 hassas bilgi gizlendi: 2 IBAN, 1 e-posta.'),
        findsOneWidget,
      );
      expect(find.text('2 sayfa okundu'), findsOneWidget);
      expect(find.byKey(const Key('original_text')), findsNothing);
    });

    testWidgets('"Bitti" goes home and forgets the result', (tester) async {
      await _openApp(tester);
      await _openAddAction(tester, '/capture/bank');
      await tester.tap(find.byKey(const Key('pick_image_button')));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.byKey(const Key('result_done_button')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('result_done_button')));
      await tester.pumpAndSettle();

      expect(find.text('Henüz harcama yok'), findsOneWidget);
      final container = ProviderScope.containerOf(
        tester.element(find.byType(Scaffold).first),
      );
      expect(container.read(captureFlowProvider), isA<CaptureIdle>());
    });
  });

  group('share from another app', () {
    testWidgets(
      'a shared PDF at start: ask the kind, read it, show the result',
      (tester) async {
        final app = await _openApp(
          tester,
          shared: [
            SharedFile(
              path: '/cache/fatura.pdf',
              isPdf: true,
              modified: DateTime(2026, 10, 5),
            ),
          ],
        );

        expect(find.text('Bu bir ne?'), findsOneWidget);
        await tester.tap(find.byKey(const Key('kind_bank')));
        await tester.pumpAndSettle();

        final input = app.pipeline.inputs.single;
        expect(input.isPdf, isTrue);
        expect(input.kind, CaptureKind.bankScreenshot);
        expect(input.source, CaptureSource.share);
        expect(input.file.path, '/cache/fatura.pdf');
        expect(input.captureDate, DateTime(2026, 10, 5));
        expect(find.text('Okunan bilgiler'), findsOneWidget);
        expect(app.sharedMedia.resets, greaterThan(0));
      },
    );

    testWidgets('an image shared while the app is open is handled too', (
      tester,
    ) async {
      final app = await _openApp(tester);
      expect(find.text('Bu bir ne?'), findsNothing);

      app.sharedMedia.controller.add([
        SharedFile(
          path: '/cache/a.jpg',
          isPdf: false,
          modified: DateTime(2026, 10, 6),
        ),
        SharedFile(
          path: '/cache/b.jpg',
          isPdf: false,
          modified: DateTime(2026, 10, 7),
        ),
      ]);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('kind_receipt')));
      await tester.pumpAndSettle();

      // Only the first file is read.
      expect(app.pipeline.inputs, hasLength(1));
      expect(app.pipeline.inputs.single.file.path, '/cache/a.jpg');
      expect(app.pipeline.inputs.single.isPdf, isFalse);
    });

    testWidgets('nothing happens when nothing is shared', (tester) async {
      final app = await _openApp(tester);
      expect(find.text('Bu bir ne?'), findsNothing);
      expect(app.pipeline.inputs, isEmpty);
    });
  });

  group('camera screen', () {
    testWidgets('says so when the phone has no camera and offers the gallery', (
      tester,
    ) async {
      await _openApp(tester, cameras: () async => []);
      await _openAddAction(tester, '/capture/scan');

      expect(find.text('Kamera bulunamadı'), findsOneWidget);
      await tester.tap(find.text('Galeriden ekle'));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('pick_image_button')), findsOneWidget);
    });

    testWidgets('explains a denied camera permission', (tester) async {
      await _openApp(
        tester,
        cameras: () async => throw CameraException('CameraAccessDenied', 'no'),
      );
      await _openAddAction(tester, '/capture/scan');

      expect(find.text('Kamera izni gerekli'), findsOneWidget);
      expect(find.text('Galeriden ekle'), findsOneWidget);
    });

    testWidgets('another camera error offers to try again', (tester) async {
      await _openApp(tester, cameras: () async => throw StateError('x'));
      await _openAddAction(tester, '/capture/scan');

      expect(find.text('Kamera açılamadı'), findsOneWidget);
      expect(find.text('Tekrar dene'), findsOneWidget);
    });
  });
}
