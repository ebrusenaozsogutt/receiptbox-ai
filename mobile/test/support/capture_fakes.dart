import 'dart:async';
import 'dart:io';

import 'package:receiptbox/core/ocr/capture_temp_dir.dart';
import 'package:receiptbox/core/ocr/ocr_service.dart';
import 'package:receiptbox/core/ocr/pdf_page_renderer.dart';
import 'package:receiptbox/core/ocr/qr_service.dart';
import 'package:receiptbox/core/ocr/reading_order.dart';
import 'package:receiptbox/core/privacy/pii_masker.dart';
import 'package:receiptbox/features/capture/data/capture_pipeline.dart';
import 'package:receiptbox/features/capture/data/media_sources.dart';
import 'package:receiptbox/features/capture/domain/capture_payload.dart';

class FakeTextEngine implements TextRecognitionEngine {
  FakeTextEngine(this.pages);

  /// One list of lines per call (= per page).
  final List<List<OcrLine>> pages;
  int calls = 0;
  bool fail = false;

  @override
  Future<List<OcrLine>> recognize(String imagePath) async {
    if (fail) throw StateError('engine failed');
    return pages[calls++ % pages.length];
  }

  @override
  Future<void> close() async {}
}

class FakeQrEngine implements QrScanEngine {
  FakeQrEngine([this.codes = const []]);

  final List<String> codes;

  @override
  Future<List<String>> scan(String imagePath) async => codes;

  @override
  Future<void> close() async {}
}

class FakePdfRenderer implements PdfPageRenderer {
  FakePdfRenderer(this.pageCount, this.pageBytes);

  final int pageCount;
  final List<int> pageBytes;
  int? askedMaxPages;

  @override
  Future<List<File>> renderFirstPages(
    File pdf,
    Directory outputDirectory, {
    int maxPages = 2,
  }) async {
    askedMaxPages = maxPages;
    final count = pageCount < maxPages ? pageCount : maxPages;
    return [
      for (var i = 0; i < count; i++)
        await File('${outputDirectory.path}/pdfpage_$i.jpg')
            .writeAsBytes(pageBytes),
    ];
  }
}

/// A temp dir whose clear() does nothing: widget tests must not do real file IO.
class NoopTempDir extends CaptureTempDir {
  NoopTempDir() : super(() async => Directory.systemTemp);

  @override
  Future<void> clear() async {}
}

/// The whole pipeline replaced: widget tests decide what a capture returns, without real files,
/// isolates or ML Kit.
class FakeCapturePipeline extends CapturePipeline {
  FakeCapturePipeline()
    : super(
        ocr: OcrService(FakeTextEngine([[]])),
        qr: QrService(FakeQrEngine()),
        pdf: FakePdfRenderer(0, const []),
        tempDir: NoopTempDir(),
        keepOriginalForDebug: true,
      );

  final List<CaptureInput> inputs = [];
  CaptureException? error;

  /// When set, process() waits for it: lets a test look at the "reading" state.
  Completer<void>? gate;

  CaptureResult result = CaptureResult(
    payload: CapturePayload(
      kind: CaptureKind.receipt,
      maskedText: 'A101 MARKET\nTel: [PHONE]\nTOPLAM  120,00',
      captureDate: DateTime(2026, 11, 18),
      source: CaptureSource.gallery,
    ),
    maskedCounts: const {PiiType.phone: 1},
    pageCount: 1,
    debugOriginalText: 'A101 MARKET\nTel: 0532 123 45 67\nTOPLAM  120,00',
  );

  @override
  Future<CaptureResult> process(CaptureInput input) async {
    inputs.add(input);
    if (gate != null) await gate!.future;
    final failure = error;
    if (failure != null) throw failure;
    return result;
  }
}

class FakeGalleryPicker implements GalleryPicker {
  PickedImage? next = PickedImage(
    file: File('${Directory.systemTemp.path}/does_not_exist_picked.jpg'),
    modified: DateTime(2026, 11, 1),
  );
  int calls = 0;
  Object? error;

  @override
  Future<PickedImage?> pickImage() async {
    calls++;
    if (error != null) throw error!;
    return next;
  }
}

class FakeSharedMediaSource implements SharedMediaSource {
  List<SharedFile> initialFiles = const [];
  final StreamController<List<SharedFile>> controller =
      StreamController.broadcast();
  int resets = 0;

  @override
  Future<List<SharedFile>> initial() async => initialFiles;

  @override
  Stream<List<SharedFile>> stream() => controller.stream;

  @override
  Future<void> reset() async => resets++;
}
