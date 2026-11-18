import 'dart:async';
import 'dart:io';

import 'package:image_picker/image_picker.dart';
import 'package:receive_sharing_intent/receive_sharing_intent.dart';

/// An image the user picked in the gallery. The file is a copy in the app's cache folder.
class PickedImage {
  const PickedImage({required this.file, required this.modified});

  final File file;

  /// When the picture was taken or saved, as far as the platform tells us.
  final DateTime modified;
}

/// A file another app shared with ReceiptBox (copied into the app's cache by the plugin).
class SharedFile {
  const SharedFile({
    required this.path,
    required this.isPdf,
    required this.modified,
  });

  final String path;
  final bool isPdf;

  /// Last-modified time of the shared copy (the best date we have for it).
  final DateTime modified;
}

/// The system photo picker. On Android 13+ it needs no storage permission at all.
abstract interface class GalleryPicker {
  Future<PickedImage?> pickImage();
}

class SystemGalleryPicker implements GalleryPicker {
  const SystemGalleryPicker();

  @override
  Future<PickedImage?> pickImage() async {
    final picked = await ImagePicker().pickImage(
      source: ImageSource.gallery,
      requestFullMetadata: false,
    );
    if (picked == null) return null;
    return PickedImage(
      file: File(picked.path),
      modified: await picked.lastModified(),
    );
  }
}

/// What other apps share with us: "Share -> ReceiptBox" for images and PDFs.
abstract interface class SharedMediaSource {
  /// Files that started the app (or were waiting when it came to the front).
  Future<List<SharedFile>> initial();

  /// Files shared while the app is already running.
  Stream<List<SharedFile>> stream();

  /// Tells the platform that the files were handled, so they are not delivered again.
  Future<void> reset();
}

class PluginSharedMediaSource implements SharedMediaSource {
  const PluginSharedMediaSource();

  ReceiveSharingIntent get _plugin => ReceiveSharingIntent.instance;

  @override
  Future<List<SharedFile>> initial() async =>
      _convert(await _plugin.getInitialMedia());

  @override
  Stream<List<SharedFile>> stream() =>
      _plugin.getMediaStream().asyncMap(_convert);

  @override
  Future<void> reset() async {
    await _plugin.reset();
  }

  /// Only images and PDFs are accepted; text, links and videos are dropped.
  static Future<List<SharedFile>> _convert(List<SharedMediaFile> files) async {
    final accepted = <SharedFile>[];
    for (final file in files) {
      final isImage = file.type == SharedMediaType.image;
      if (!isImage && !_isPdf(file)) continue;
      accepted.add(
        SharedFile(
          path: file.path,
          isPdf: !isImage,
          modified: await _modified(file.path),
        ),
      );
    }
    return accepted;
  }

  static Future<DateTime> _modified(String path) async {
    try {
      return await File(path).lastModified();
    } on FileSystemException {
      return DateTime.now();
    }
  }

  static bool _isPdf(SharedMediaFile file) =>
      file.type == SharedMediaType.file &&
      (file.mimeType == 'application/pdf' ||
          file.path.toLowerCase().endsWith('.pdf'));
}
