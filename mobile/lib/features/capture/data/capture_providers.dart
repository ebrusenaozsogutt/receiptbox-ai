import 'package:camera/camera.dart';
import 'package:path_provider/path_provider.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../core/ocr/capture_temp_dir.dart';
import '../../../core/ocr/ocr_service.dart';
import '../../../core/ocr/pdf_page_renderer.dart';
import '../../../core/ocr/qr_service.dart';
import '../domain/capture_payload.dart';
import 'capture_pipeline.dart';
import 'media_sources.dart';

part 'capture_providers.g.dart';

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

/// Lists the phone's cameras. Overridden in tests (there is no camera in a unit test).
@Riverpod(keepAlive: true)
Future<List<CameraDescription>> Function() camerasLoader(Ref ref) =>
    availableCameras;

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

  void reset() {
    if (ref.mounted) state = const CaptureIdle();
  }

  static String _retryRoute(CaptureInput input) {
    if (input.source == CaptureSource.camera) return '/capture/scan';
    if (input.source == CaptureSource.share) return '/home';
    return input.kind == CaptureKind.bankScreenshot
        ? '/capture/bank'
        : '/capture/gallery';
  }
}
