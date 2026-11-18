// Real-device check of the P04 capture pipeline: the REAL ML Kit OCR + QR, the real PDF renderer
// and the real image code, on SYNTHETIC samples (no real receipts). Needs no backend. Not part
// of CI (CI has no emulator).
//
// The samples are served from the PC for a moment (flutter test re-installs the app, which
// wipes any file pushed to the emulator before):
//
//   uv run --with pillow --with "qrcode[pil]" python ai/experiments/make_synthetic_samples.py
//   python -m http.server 8765 --directory ai/datasets/synthetic        # keep running
//   flutter test integration_test/capture_e2e_test.dart -d emulator-5554
//
// "Works offline" check: add --dart-define=EXPECT_OFFLINE=true. After downloading the samples
// the test prints SAMPLES_READY and waits (up to 2 minutes) until the network is really gone;
// meanwhile switch the emulator to airplane mode:
//
//   adb shell cmd connectivity airplane-mode enable
//
// Only then are the images read, so everything below ran without any network.

import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:path_provider/path_provider.dart';
import 'package:receiptbox/core/ocr/capture_temp_dir.dart';
import 'package:receiptbox/core/ocr/ocr_service.dart';
import 'package:receiptbox/core/ocr/pdf_page_renderer.dart';
import 'package:receiptbox/core/ocr/qr_service.dart';
import 'package:receiptbox/core/privacy/pii_masker.dart';
import 'package:receiptbox/features/capture/data/capture_pipeline.dart';
import 'package:receiptbox/features/capture/domain/capture_payload.dart';

const _samplesUrl = String.fromEnvironment(
  'SAMPLES_URL',
  defaultValue: 'http://10.0.2.2:8765',
);
const _expectOffline = bool.fromEnvironment('EXPECT_OFFLINE');
const _sampleNames = [
  'receipt_market.jpg',
  'receipt_rotated.jpg',
  'receipt_gib_qr.jpg',
  'bank_screenshot.jpg',
  'invoice_2pages.pdf',
  'not_a_receipt.jpg',
];

late Directory _samples;
late CaptureTempDir _tempDir;
late CapturePipeline _pipeline;

/// Fetches the synthetic samples from the PC (the only network use of this test).
Future<void> _download() async {
  final client = HttpClient();
  try {
    for (final name in _sampleNames) {
      final request = await client.getUrl(Uri.parse('$_samplesUrl/$name'));
      final response = await request.close();
      if (response.statusCode != 200) {
        fail(
          '$_samplesUrl/$name answered ${response.statusCode}. Is the sample server running?',
        );
      }
      final bytes = BytesBuilder();
      await response.forEach(bytes.add);
      await File('${_samples.path}/$name').writeAsBytes(bytes.takeBytes());
    }
  } finally {
    client.close(force: true);
  }
}

/// Waits until the PC cannot be reached any more (airplane mode), so that the pipeline below
/// provably runs without a network.
Future<void> _waitUntilOffline() async {
  // ignore: avoid_print
  print('SAMPLES_READY: switch the emulator to airplane mode now');
  final deadline = DateTime.now().add(const Duration(minutes: 2));
  while (DateTime.now().isBefore(deadline)) {
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 2);
    try {
      final request = await client.getUrl(
        Uri.parse('$_samplesUrl/receipt_market.jpg'),
      );
      await (await request.close()).drain<void>();
    } on Object {
      // ignore: avoid_print
      print('OFFLINE_CONFIRMED');
      return;
    } finally {
      client.close(force: true);
    }
    await Future<void>.delayed(const Duration(seconds: 1));
  }
  fail(
    'The network was still reachable after 2 minutes (airplane mode not on?).',
  );
}

Future<File> _copyOf(String name) async {
  final source = File('${_samples.path}/$name');
  if (!source.existsSync()) {
    fail(
      '$name was not downloaded from $_samplesUrl (see the top of this file).',
    );
  }
  final work = await Directory.systemTemp.createTemp('sample');
  return source.copy('${work.path}/$name');
}

Future<CaptureResult> _read(
  String name, {
  CaptureKind kind = CaptureKind.receipt,
  bool isPdf = false,
}) async {
  return _pipeline.process(
    CaptureInput(
      file: await _copyOf(name),
      isPdf: isPdf,
      kind: kind,
      source: CaptureSource.gallery,
      captureDate: DateTime(2026, 11, 18),
    ),
  );
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    _samples = await Directory.systemTemp.createTemp('synthetic_samples');
    await _download();
    if (_expectOffline) await _waitUntilOffline();
    _tempDir = CaptureTempDir(getTemporaryDirectory);
    await _tempDir.clear();
    _pipeline = CapturePipeline(
      ocr: OcrService(MlKitTextRecognitionEngine()),
      qr: QrService(MlKitQrScanEngine()),
      pdf: const PdfxPageRenderer(),
      tempDir: _tempDir,
      keepOriginalForDebug: true,
    );
  });

  tearDownAll(() async {
    // No image may be left behind by any of the runs.
    final left = Directory(
      '${(await getTemporaryDirectory()).path}/capture_tmp',
    );
    expect(!left.existsSync() || left.listSync().isEmpty, isTrue);
  });

  testWidgets('receipt photo: text is read, personal data is masked', (
    tester,
  ) async {
    final result = await tester.runAsync(() => _read('receipt_market.jpg'));
    final masked = result!.payload.maskedText;
    final original = result.debugOriginalText!;

    // Receipt content survives (amounts, merchant, items).
    expect(masked, contains('TOPLAM'));
    expect(masked, contains('270,30'));
    expect(masked, contains('MARKET'));
    // The OCR really saw the personal data ...
    expect(original, contains('4111'));
    // ... and none of it is left after masking.
    expect(masked, isNot(contains('0532')));
    expect(masked, isNot(contains('4111')));
    expect(masked, isNot(contains('Örnek')));
    expect(result.maskedCounts[PiiType.phone], greaterThanOrEqualTo(1));
    expect(result.maskedCounts[PiiType.card], greaterThanOrEqualTo(1));
    expect(result.maskedCounts[PiiType.name], greaterThanOrEqualTo(1));
    expect(result.payload.qrPayload, isNull);
  });

  testWidgets('a photo with EXIF rotation is read upright', (tester) async {
    final result = await tester.runAsync(() => _read('receipt_rotated.jpg'));
    expect(result!.payload.maskedText, contains('TOPLAM'));
    expect(result.payload.maskedText, contains('270,30'));
  });

  testWidgets('GİB QR code is found and the buyer TCKN is removed', (
    tester,
  ) async {
    final result = await tester.runAsync(() => _read('receipt_gib_qr.jpg'));
    final qr = result!.payload.qrPayload;
    expect(qr, isNotNull);
    expect(qr!['ettn'], '11111111-2222-3333-4444-555555555555');
    expect(qr['odenecek'], '270.30');
    expect(qr.containsKey('avkntckn'), isFalse);
    expect(result.payload.toJson().toString(), isNot(contains('12345678901')));
  });

  testWidgets('bank screenshot: IBAN, balance and card are masked', (
    tester,
  ) async {
    final result = await tester.runAsync(
      () => _read('bank_screenshot.jpg', kind: CaptureKind.bankScreenshot),
    );
    final masked = result!.payload.maskedText;
    expect(masked, isNot(contains('TR33')));
    expect(masked, isNot(contains('12.345,67')));
    expect(masked, isNot(contains('4111')));
    expect(masked, isNot(contains('Örnek'))); // account holder
    expect(result.maskedCounts[PiiType.iban], greaterThanOrEqualTo(1));
    expect(result.maskedCounts[PiiType.balance], greaterThanOrEqualTo(1));
    // The spending rows stay readable.
    expect(masked, contains('A101'));
    expect(masked, contains('270,30'));
  });

  testWidgets('a 2-page PDF is rendered and read', (tester) async {
    final result = await tester.runAsync(
      () => _read('invoice_2pages.pdf', isPdf: true),
    );
    expect(result!.pageCount, 2);
    expect(result.payload.maskedText, contains('2.499,00'));
    expect(result.payload.maskedText, isNot(contains('Mehmet')));
  });

  testWidgets('an image without text gives noTextFound', (tester) async {
    await tester.runAsync(() async {
      await expectLater(
        _read('not_a_receipt.jpg'),
        throwsA(
          isA<CaptureException>().having(
            (e) => e.failure,
            'failure',
            CaptureFailure.noTextFound,
          ),
        ),
      );
    });
  });
}
