import 'dart:async';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../data/capture_providers.dart';
import '../data/media_sources.dart';
import '../domain/capture_payload.dart';
import 'capture_kind_sheet.dart';

/// Sits around the main screens and reacts to "Share -> ReceiptBox" from other apps:
/// asks whether it is a receipt or a bank screenshot, reads it on the phone and opens the
/// result screen. Also wipes leftovers of an earlier run from the temporary capture folder.
class SharedMediaListener extends ConsumerStatefulWidget {
  const SharedMediaListener({super.key, required this.child});

  final Widget child;

  @override
  ConsumerState<SharedMediaListener> createState() =>
      _SharedMediaListenerState();
}

class _SharedMediaListenerState extends ConsumerState<SharedMediaListener> {
  StreamSubscription<List<SharedFile>>? _subscription;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    unawaited(_start());
  }

  Future<void> _start() async {
    final source = ref.read(sharedMediaSourceProvider);
    try {
      await ref.read(captureTempDirProvider).clear();
      final initial = await source.initial();
      if (!mounted) return;
      _subscription = source.stream().listen(
        (files) => unawaited(_handle(files)),
        onError: (_) {}, // sharing is a convenience: a plugin hiccup must not crash the app
      );
      await _handle(initial);
    } on Object {
      // No sharing support (or no platform at all, as in unit tests): everything else works.
    }
  }

  Future<void> _handle(List<SharedFile> files) async {
    if (files.isEmpty || _busy || !mounted) return;
    _busy = true;
    final source = ref.read(sharedMediaSourceProvider);
    try {
      // One file at a time: the first one is read, the others are dropped.
      final shared = files.first;
      final file = File(shared.path);
      final kind = await askCaptureKind(context);
      if (!mounted) return;
      if (kind == null) {
        try {
          await file.delete();
        } on FileSystemException {
          // Nothing to do.
        }
        return;
      }
      unawaited(
        ref
            .read(captureFlowProvider.notifier)
            .process(
              CaptureInput(
                file: file,
                isPdf: shared.isPdf,
                kind: kind,
                source: CaptureSource.share,
                captureDate: shared.modified,
              ),
            ),
      );
      if (!mounted) return;
      unawaited(context.push('/capture/result'));
    } finally {
      _busy = false;
      unawaited(source.reset().catchError((_) {}));
    }
  }

  @override
  void dispose() {
    unawaited(_subscription?.cancel());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
