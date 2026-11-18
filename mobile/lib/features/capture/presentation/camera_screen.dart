import 'dart:async';
import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/loading_view.dart';
import '../data/capture_providers.dart';
import '../domain/capture_payload.dart';

enum _CameraStatus { starting, ready, noCamera, permissionDenied, failed }

/// "Fiş Tara": live camera preview and a shutter button. The picture is read on the phone
/// and never stored (see CapturePipeline).
///
/// NOT verifiable on the emulator's default camera: the real camera check on a phone is a
/// known gap in docs/PROGRESS.md.
class CameraScreen extends ConsumerStatefulWidget {
  const CameraScreen({super.key});

  @override
  ConsumerState<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends ConsumerState<CameraScreen>
    with WidgetsBindingObserver {
  CameraController? _controller;
  _CameraStatus _status = _CameraStatus.starting;
  bool _taking = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_start());
  }

  Future<void> _start() async {
    try {
      final cameras = await ref.read(camerasLoaderProvider)();
      if (!mounted) return;
      if (cameras.isEmpty) {
        setState(() => _status = _CameraStatus.noCamera);
        return;
      }
      final back = cameras.firstWhere(
        (camera) => camera.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );
      final controller = CameraController(
        back,
        ResolutionPreset.high,
        enableAudio: false,
      );
      _controller = controller;
      await controller.initialize();
      if (!mounted) return;
      setState(() => _status = _CameraStatus.ready);
    } on CameraException catch (error) {
      if (!mounted) return;
      final denied =
          error.code == 'CameraAccessDenied' ||
          error.code == 'CameraAccessDeniedWithoutPrompt' ||
          error.code == 'CameraAccessRestricted';
      setState(
        () => _status = denied
            ? _CameraStatus.permissionDenied
            : _CameraStatus.failed,
      );
    } on Object {
      if (!mounted) return;
      setState(() => _status = _CameraStatus.failed);
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) return;
    if (state == AppLifecycleState.inactive) {
      // The camera must be released when the app goes to the background.
      _controller = null;
      setState(() => _status = _CameraStatus.starting);
      unawaited(controller.dispose());
    } else if (state == AppLifecycleState.resumed) {
      unawaited(_start());
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    unawaited(_controller?.dispose());
    super.dispose();
  }

  Future<void> _takePicture() async {
    final controller = _controller;
    if (_taking || controller == null || !controller.value.isInitialized) {
      return;
    }
    setState(() => _taking = true);
    try {
      final photo = await controller.takePicture();
      if (!mounted) return;
      unawaited(
        ref
            .read(captureFlowProvider.notifier)
            .process(
              CaptureInput(
                file: File(photo.path),
                kind: CaptureKind.receipt,
                source: CaptureSource.camera,
                captureDate: DateTime.now(),
              ),
            ),
      );
      context.pushReplacement('/capture/result');
    } on Object {
      if (!mounted) return;
      setState(() {
        _taking = false;
        _status = _CameraStatus.failed;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.cameraBackground,
      appBar: AppBar(
        title: const Text('Fiş Tara'),
        backgroundColor: AppColors.cameraBackground,
        foregroundColor: AppColors.cameraForeground,
      ),
      body: switch (_status) {
        _CameraStatus.starting => const LoadingView(),
        _CameraStatus.ready => _Preview(
          controller: _controller!,
          taking: _taking,
          onShutter: _takePicture,
        ),
        _CameraStatus.permissionDenied => _Fallback(
          icon: Icons.no_photography_outlined,
          title: 'Kamera izni gerekli',
          message:
              'Fiş çekebilmek için kamera iznini Android ayarlarından açabilirsin. '
              'İstersen galeriden de ekleyebilirsin.',
        ),
        _CameraStatus.noCamera => _Fallback(
          icon: Icons.videocam_off_outlined,
          title: 'Kamera bulunamadı',
          message: 'Bu cihazda kullanılabilir bir kamera yok.',
        ),
        _CameraStatus.failed => _Fallback(
          icon: Icons.error_outline,
          title: 'Kamera açılamadı',
          message: 'Tekrar dene ya da galeriden ekle.',
          onRetry: () {
            setState(() => _status = _CameraStatus.starting);
            unawaited(_start());
          },
        ),
      },
    );
  }
}

class _Preview extends StatelessWidget {
  const _Preview({
    required this.controller,
    required this.taking,
    required this.onShutter,
  });

  final CameraController controller;
  final bool taking;
  final VoidCallback onShutter;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Column(
        children: [
          Expanded(child: Center(child: CameraPreview(controller))),
          Padding(
            padding: const EdgeInsets.all(AppSpacing.xxl),
            child: Semantics(
              button: true,
              label: 'Fotoğraf çek',
              child: GestureDetector(
                key: const Key('shutter_button'),
                onTap: taking ? null : onShutter,
                child: Container(
                  width: AppSizes.shutterButton,
                  height: AppSizes.shutterButton,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: taking
                        ? AppColors.textSubtle
                        : AppColors.cameraForeground,
                    border: Border.all(
                      color: AppColors.cameraBackground,
                      width: AppSizes.shutterRing,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Fallback extends StatelessWidget {
  const _Fallback({
    required this.icon,
    required this.title,
    required this.message,
    this.onRetry,
  });

  final IconData icon;
  final String title;
  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    // The rest of the app is light; the fallback sits on the dark camera background, so it
    // is drawn on a light card.
    return Container(
      color: AppColors.bg,
      child: EmptyState(
        icon: icon,
        title: title,
        message: message,
        actionLabel: onRetry != null ? 'Tekrar dene' : 'Galeriden ekle',
        onAction: onRetry ?? () => context.pushReplacement('/capture/gallery'),
      ),
    );
  }
}
