import 'dart:async';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../data/capture_providers.dart';
import '../domain/capture_payload.dart';
import 'capture_kind_sheet.dart';

/// Sits around the main screens and reacts to "Share -> ReceiptBox" from other apps (the files
/// wait in [sharedInboxProvider] until the user is signed in and these screens exist): asks
/// whether it is a receipt or a bank screenshot, reads it on the phone and opens the result
/// screen. Also wipes leftovers of an earlier run from the temporary capture folder.
class SharedMediaListener extends ConsumerStatefulWidget {
  const SharedMediaListener({super.key, required this.child});

  final Widget child;

  @override
  ConsumerState<SharedMediaListener> createState() =>
      _SharedMediaListenerState();
}

class _SharedMediaListenerState extends ConsumerState<SharedMediaListener> {
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    unawaited(ref.read(captureTempDirProvider).clear().catchError((_) {}));
    // Something may already be waiting (the app was started by the share).
    WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(_drain()));
  }

  Future<void> _drain() async {
    if (_busy || !mounted) return;
    final files = ref.read(sharedInboxProvider.notifier).take();
    if (files.isEmpty) return;
    _busy = true;
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
      unawaited(context.push('/capture/result'));
    } finally {
      _busy = false;
      // Another share may have arrived while the sheet was open.
      if (mounted && ref.read(sharedInboxProvider).isNotEmpty) {
        unawaited(_drain());
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(sharedInboxProvider, (previous, next) {
      if (next.isNotEmpty) unawaited(_drain());
    });
    return widget.child;
  }
}
