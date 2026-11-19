import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:receiptbox/core/ocr/capture_temp_dir.dart';
import 'package:receiptbox/core/ocr/ocr_service.dart';
import 'package:receiptbox/core/ocr/qr_service.dart';
import 'package:receiptbox/core/ocr/reading_order.dart';
import 'package:receiptbox/core/privacy/pii_masker.dart';
import 'package:receiptbox/features/capture/data/capture_pipeline.dart';
import 'package:receiptbox/features/capture/domain/capture_payload.dart';

import '../../support/capture_fakes.dart';

Uint8List _tinyJpeg() =>
    Uint8List.fromList(img.encodeJpg(img.Image(width: 40, height: 40)));

OcrLine _line(String text, double top) =>
    OcrLine(text: text, left: 0, top: top, right: 100, bottom: top + 20);

void main() {
  late Directory root;
  late CaptureTempDir tempDir;

  setUp(() async {
    root = await Directory.systemTemp.createTemp('capture_pipeline_test');
    tempDir = CaptureTempDir(() async => root);
  });

  tearDown(() async {
    if (await root.exists()) await root.delete(recursive: true);
  });

  Future<File> inputImage() async {
    final file = File('${root.path}/input.jpg');
    return file.writeAsBytes(_tinyJpeg());
  }

  CapturePipeline pipeline({
    required FakeTextEngine text,
    FakeQrEngine? qr,
    FakePdfRenderer? pdf,
    bool keepOriginal = false,
  }) => CapturePipeline(
    ocr: OcrService(text),
    qr: QrService(qr ?? FakeQrEngine()),
    pdf: pdf ?? FakePdfRenderer(1, _tinyJpeg()),
    tempDir: tempDir,
    keepOriginalForDebug: keepOriginal,
  );

  CaptureInput input(
    File file, {
    bool isPdf = false,
    CaptureKind kind = CaptureKind.receipt,
  }) => CaptureInput(
    file: file,
    isPdf: isPdf,
    kind: kind,
    source: CaptureSource.gallery,
    captureDate: DateTime(2026, 11, 18),
  );

  final receipt = [
    [
      _line('A101 MARKET', 0),
      _line('Müşteri: Ahmet Yılmaz', 30),
      _line('Tel: 0532 123 45 67', 60),
      _line('TOPLAM  *120,00', 90),
    ],
  ];

  test('masks the text and builds the payload for the backend', () async {
    final result = await pipeline(text: FakeTextEngine(receipt))
        .process(input(await inputImage()));

    final json = result.payload.toJson();
    expect(json['kind'], 'RECEIPT');
    expect(json['source'], 'GALLERY');
    expect(json['capture_date'], '2026-11-18');
    expect(json.containsKey('qr_payload'), isFalse);
    final masked = json['masked_text'] as String;
    expect(masked, contains('A101 MARKET'));
    expect(masked, contains('120,00'));
    expect(masked, isNot(contains('0532')));
    expect(masked, contains('[PHONE]'));
    expect(masked, isNot(contains('Yılmaz')));
    expect(result.maskedCounts[PiiType.phone], 1);
  });

  test('the original text is dropped in release mode', () async {
    final result = await pipeline(text: FakeTextEngine(receipt))
        .process(input(await inputImage()));
    expect(result.debugOriginalText, isNull);
  });

  test('the original text is kept only when debug mode asks for it', () async {
    final result = await pipeline(
      text: FakeTextEngine(receipt),
      keepOriginal: true,
    ).process(input(await inputImage()));
    expect(result.debugOriginalText, contains('0532 123 45 67'));
    expect(result.payload.maskedText, isNot(contains('0532 123 45 67')));
  });

  test('a GİB QR code is attached and the buyer TCKN is not in it', () async {
    const qr =
        '{"ettn":"abc-123","avkntckn":"12345678901","odenecek":"120.00","vergidahil":"120.00"}';
    final result = await pipeline(
      text: FakeTextEngine(receipt),
      qr: FakeQrEngine([qr]),
    ).process(input(await inputImage()));

    final payload = result.payload.qrPayload!;
    expect(payload['ettn'], 'abc-123');
    expect(payload.containsKey('avkntckn'), isFalse);
    expect(result.payload.toJson().toString(), isNot(contains('12345678901')));
  });

  test('a QR code that is not a GİB invoice is ignored', () async {
    final result = await pipeline(
      text: FakeTextEngine(receipt),
      qr: FakeQrEngine(['https://example.com/wifi-password-1234']),
    ).process(input(await inputImage()));
    expect(result.payload.qrPayload, isNull);
  });

  test(
    'a PDF is rendered to at most 2 pages and the texts are joined',
    () async {
      final text = FakeTextEngine([
        [_line('SAYFA BİR', 0)],
        [_line('SAYFA İKİ', 0)],
      ]);
      final pdf = FakePdfRenderer(5, _tinyJpeg());
      final file = await File('${root.path}/in.pdf').writeAsBytes([1, 2, 3]);

      final result = await pipeline(
        text: text,
        pdf: pdf,
      ).process(input(file, isPdf: true));

      expect(pdf.askedMaxPages, 2);
      expect(result.pageCount, 2);
      expect(result.payload.maskedText, 'SAYFA BİR\n\nSAYFA İKİ');
    },
  );

  test('an unreadable PDF gives unsupportedFile', () async {
    final file = await File('${root.path}/in.pdf').writeAsBytes([1, 2, 3]);
    await expectLater(
      pipeline(
        text: FakeTextEngine(receipt),
        pdf: FakePdfRenderer(0, _tinyJpeg()),
      ).process(input(file, isPdf: true)),
      throwsA(
        isA<CaptureException>().having(
          (e) => e.failure,
          'failure',
          CaptureFailure.unsupportedFile,
        ),
      ),
    );
  });

  test('a file that is not an image gives unsupportedFile', () async {
    final file = await File('${root.path}/in.jpg').writeAsBytes([1, 2, 3]);
    await expectLater(
      pipeline(text: FakeTextEngine(receipt)).process(input(file)),
      throwsA(
        isA<CaptureException>().having(
          (e) => e.failure,
          'failure',
          CaptureFailure.unsupportedFile,
        ),
      ),
    );
  });

  test('an image without any text gives noTextFound', () async {
    await expectLater(
      pipeline(text: FakeTextEngine([[]])).process(input(await inputImage())),
      throwsA(
        isA<CaptureException>().having(
          (e) => e.failure,
          'failure',
          CaptureFailure.noTextFound,
        ),
      ),
    );
  });

  test('an OCR engine failure gives readFailed and no message from the engine leaks', () async {
    final engine = FakeTextEngine(receipt)..fail = true;
    await expectLater(
      pipeline(text: engine).process(input(await inputImage())),
      throwsA(
        isA<CaptureException>()
            .having((e) => e.failure, 'failure', CaptureFailure.readFailed)
            .having(
              (e) => e.message,
              'message',
              isNot(contains('engine failed')),
            ),
      ),
    );
  });

  test('all image files are deleted afterwards, also when it fails', () async {
    final file = await inputImage();
    await pipeline(text: FakeTextEngine(receipt)).process(input(file));
    expect(file.existsSync(), isFalse);
    expect(Directory('${root.path}/capture_tmp').listSync(), isEmpty);

    final failing = await File('${root.path}/bad.jpg').writeAsBytes([9, 9, 9]);
    await expectLater(
      pipeline(text: FakeTextEngine(receipt)).process(input(failing)),
      throwsA(isA<CaptureException>()),
    );
    expect(failing.existsSync(), isFalse);
    expect(Directory('${root.path}/capture_tmp').listSync(), isEmpty);
  });

  test('the input file is kept when deleteInput is false', () async {
    final file = await inputImage();
    await pipeline(text: FakeTextEngine(receipt)).process(
      CaptureInput(
        file: file,
        kind: CaptureKind.receipt,
        source: CaptureSource.camera,
        captureDate: DateTime(2026, 1, 1),
        deleteInput: false,
      ),
    );
    expect(file.existsSync(), isTrue);
  });

  group('keeping the image for the review screen (P07)', () {
    CaptureInput keepInput(File file, {CaptureKind kind = CaptureKind.receipt, bool isPdf = false}) =>
        CaptureInput(
          file: file,
          isPdf: isPdf,
          kind: kind,
          source: CaptureSource.gallery,
          captureDate: DateTime(2026, 11, 18),
          keepImage: true,
        );

    test('a receipt photo is kept as a clean JPEG copy', () async {
      final result = await pipeline(text: FakeTextEngine(receipt))
          .process(keepInput(await inputImage()));

      final kept = result.retainedImage!;
      expect(kept.existsSync(), isTrue);
      expect(kept.path.endsWith('.jpg'), isTrue);
      expect(result.retainedIsPdf, isFalse);
      // Only the kept copy is left in the temporary folder.
      expect(Directory('${root.path}/capture_tmp').listSync(), hasLength(1));
    });

    test('nothing is kept unless it is asked for', () async {
      final result = await pipeline(text: FakeTextEngine(receipt))
          .process(input(await inputImage()));
      expect(result.retainedImage, isNull);
    });

    test('a bank screenshot is never kept, even when asked', () async {
      final result = await pipeline(text: FakeTextEngine(receipt)).process(
        keepInput(await inputImage(), kind: CaptureKind.bankScreenshot),
      );
      expect(result.retainedImage, isNull);
      expect(Directory('${root.path}/capture_tmp').listSync(), isEmpty);
    });

    test('a PDF is kept as the original file', () async {
      final pdfFile = await File('${root.path}/fatura.pdf').writeAsBytes([1, 2, 3]);
      final result = await pipeline(text: FakeTextEngine(receipt))
          .process(keepInput(pdfFile, isPdf: true));

      expect(result.retainedIsPdf, isTrue);
      expect(await result.retainedImage!.readAsBytes(), [1, 2, 3]);
    });

    test('nothing stays behind when the reading fails', () async {
      final failing = FakeTextEngine(receipt)..fail = true;
      await expectLater(
        pipeline(text: failing).process(keepInput(await inputImage())),
        throwsA(isA<CaptureException>()),
      );
      expect(Directory('${root.path}/capture_tmp').listSync(), isEmpty);
    });
  });

  test('CaptureTempDir.clear removes leftovers of an earlier run', () async {
    final dir = await tempDir.ensure();
    await File('${dir.path}/left_over.jpg').writeAsBytes([1]);
    await tempDir.clear();
    expect(dir.existsSync(), isFalse);
  });
}
