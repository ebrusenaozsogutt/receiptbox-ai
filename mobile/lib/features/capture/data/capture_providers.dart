import 'dart:async';
import 'dart:io';

import 'package:camera/camera.dart';
import 'package:path_provider/path_provider.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../core/ocr/capture_temp_dir.dart';
import '../../../core/ocr/ocr_service.dart';
import '../../../core/ocr/pdf_page_renderer.dart';
import '../../../core/ocr/qr_service.dart';
import '../domain/capture_payload.dart';
import '../../../core/networking/dio_provider.dart';
import '../../../core/storage/settings_store.dart';
import 'capture_pipeline.dart';
import 'extraction_api.dart';
import 'media_sources.dart';

part 'capture_providers.g.dart';

/// The backend's extraction endpoints (used by the debug panel; P07 uses it for real).
@Riverpod(keepAlive: true)
ExtractionApi extractionApi(Ref ref) =>
    DioExtractionApi(ref.watch(dioProvider));

@Riverpod(keepAlive: true)
CaptureTempDir captureTempDir(Ref ref) => CaptureTempDir(getTemporaryDirectory);

/// The on-device pipeline with the real ML Kit engines. Tests override this with fakes.
@Riverpod(keepAlive: true)
CapturePipeline capturePipeline(Ref ref) {
  final textEngine = MlKitTextRecognitionEngine();
  final qrEngine = MlKitQrScanEngine();
  ref.onDispose(() {
    textEngine.close();
    qrEngine.close();
  });
  return CapturePipeline(
    ocr: OcrService(textEngine),
    qr: QrService(qrEngine),
    pdf: const PdfxPageRenderer(),
    tempDir: ref.watch(captureTempDirProvider),
  );
}

@Riverpod(keepAlive: true)
GalleryPicker galleryPicker(Ref ref) => const SystemGalleryPicker();

@Riverpod(keepAlive: true)
SharedMediaSource sharedMediaSource(Ref ref) => const PluginSharedMediaSource();

/// Files other apps shared with ReceiptBox that nobody has handled yet.
///
/// This listens from the moment the app starts: the share plugin does not replay a share that
/// arrives while no one is listening (for example during the splash or login screen), so the
/// files are parked here until the main screens ask for them with [take].
@Riverpod(keepAlive: true)
class SharedInbox extends _$SharedInbox {
  @override
  List<SharedFile> build() {
    final source = ref.read(sharedMediaSourceProvider);
    final subscription = source.stream().listen(_add, onError: (_) {});
    ref.onDispose(subscription.cancel);
    // Sharing is a convenience: a plugin problem must never stop the app.
    unawaited(source.initial().then(_add, onError: (_) {}));
    return const [];
  }

  void _add(List<SharedFile> files) {
    if (files.isEmpty || !ref.mounted) return;
    state = [...state, ...files];
  }

  /// Hands over everything waiting and tells the platform it was received.
  List<SharedFile> take() {
    final taken = state;
    if (taken.isEmpty) return taken;
    state = const [];
    unawaited(ref.read(sharedMediaSourceProvider).reset().catchError((_) {}));
    return taken;
  }
}

/// Lists the phone's cameras. Overridden in tests (there is no camera in a unit test).
@Riverpod(keepAlive: true)
Future<List<CameraDescription>> Function() camerasLoader(Ref ref) =>
    availableCameras;

/// Where a finished capture is shown: receipts and invoices go to the review screen, bank
/// screenshots to the bank import screen.
String captureRouteFor(CaptureKind kind) =>
    kind == CaptureKind.receipt ? '/capture/review' : '/capture/bank-import';

/// Where the capture currently is. The result screen shows whatever this says.
sealed class CaptureFlowState {
  const CaptureFlowState();
}

class CaptureIdle extends CaptureFlowState {
  const CaptureIdle();
}

class CaptureProcessing extends CaptureFlowState {
  const CaptureProcessing({required this.retryRoute});

  /// Where "Tekrar dene" leads if this capture fails.
  final String retryRoute;
}

class CaptureDone extends CaptureFlowState {
  const CaptureDone(this.result);

  final CaptureResult result;
}

class CaptureFailed extends CaptureFlowState {
  const CaptureFailed({required this.message, required this.retryRoute});

  final String message;
  final String retryRoute;
}

/// Runs one capture at a time and keeps its outcome for the result screen. The outcome is
/// only held in memory; leaving the result screen calls [reset].
@Riverpod(keepAlive: true)
class CaptureFlow extends _$CaptureFlow {
  @override
  CaptureFlowState build() => const CaptureIdle();

  /// The state changes to "processing" before the first await, so a screen can start this
  /// without waiting and open the result screen right away.
  Future<void> process(CaptureInput input) async {
    if (state is CaptureProcessing) return;
    // One place decides what is kept: only receipts, only if the user keeps receipt images.
    input = input.copyWith(
      keepImage:
          input.kind == CaptureKind.receipt &&
          ref.read(keepReceiptImagesProvider),
    );
    final retryRoute = _retryRoute(input);
    state = CaptureProcessing(retryRoute: retryRoute);
    try {
      final result = await ref.read(capturePipelineProvider).process(input);
      if (!ref.mounted) return;
      state = CaptureDone(result);
    } on CaptureException catch (error) {
      if (!ref.mounted) return;
      state = CaptureFailed(message: error.message, retryRoute: retryRoute);
    } on Object {
      if (!ref.mounted) return;
      // Deliberately no error text: it could contain a file path or image content.
      state = CaptureFailed(
        message: const CaptureException(CaptureFailure.readFailed).message,
        retryRoute: retryRoute,
      );
    }
  }

  /// Forget the outcome AND delete the kept image, if any (nobody took it over).
  void reset() {
    if (!ref.mounted) return;
    final current = state;
    if (current is CaptureDone) {
      unawaited(_deleteQuietly(current.result.retainedImage));
    }
    state = const CaptureIdle();
  }

  /// The review screen takes over the outcome and with it the duty to delete the kept image.
  CaptureResult? handOver() {
    if (!ref.mounted) return null;
    final current = state;
    if (current is! CaptureDone) return null;
    state = const CaptureIdle();
    return current.result;
  }

  /// Debug only: show the outcome again on the "Okunan bilgiler" screen (without the kept
  /// image, which stays with the review screen).
  void showForDebug(CaptureResult result) {
    if (!ref.mounted) return;
    state = CaptureDone(result.withoutRetainedImage());
  }

  static Future<void> _deleteQuietly(File? file) async {
    try {
      if (file != null && await file.exists()) await file.delete();
    } on FileSystemException {
      // The temp folder is cleared at the next start.
    }
  }

  static String _retryRoute(CaptureInput input) {
    if (input.source == CaptureSource.camera) return '/capture/scan';
    if (input.source == CaptureSource.share) return '/home';
    return input.kind == CaptureKind.bankScreenshot
        ? '/capture/bank'
        : '/capture/gallery';
  }
}
