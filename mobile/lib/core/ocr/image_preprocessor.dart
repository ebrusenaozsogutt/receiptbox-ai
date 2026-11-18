import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show compute;
import 'package:image/image.dart' as img;

class UnsupportedImageException implements Exception {
  const UnsupportedImageException();

  @override
  String toString() => 'UnsupportedImageException';
}

/// Makes an image ready for OCR: rotates it upright by its EXIF orientation and scales the
/// long edge down to at most [maxLongEdge] pixels. No other image processing.
///
/// The result is a NEW JPEG without any metadata: the EXIF block (camera, GPS location...) is
/// not copied. The caller owns the new file and must delete it.
class ImagePreprocessor {
  const ImagePreprocessor();

  static const maxLongEdge = 2000;
  static const _jpegQuality = 90;

  Future<File> prepare(File source, Directory outputDirectory) async {
    final bytes = await source.readAsBytes();
    // Decoding a 12-megapixel photo takes a moment: do it away from the UI thread.
    final processed = await compute(processBytes, bytes);
    final output = File(
      '${outputDirectory.path}${Platform.pathSeparator}page_${DateTime.now().microsecondsSinceEpoch}.jpg',
    );
    await output.writeAsBytes(processed, flush: true);
    return output;
  }

  /// The pure part (also used by the tests): bytes in, JPEG bytes out.
  /// Throws [UnsupportedImageException] when the bytes are not an image Dart can read.
  static Uint8List processBytes(Uint8List bytes) {
    final decoded = img.decodeImage(bytes);
    if (decoded == null) throw const UnsupportedImageException();

    var image = img.bakeOrientation(
      decoded,
    ); // applies the EXIF rotation, then clears the tag
    final longEdge = image.width > image.height ? image.width : image.height;
    if (longEdge > maxLongEdge) {
      image = image.width >= image.height
          ? img.copyResize(
              image,
              width: maxLongEdge,
              interpolation: img.Interpolation.average,
            )
          : img.copyResize(
              image,
              height: maxLongEdge,
              interpolation: img.Interpolation.average,
            );
    }
    return Uint8List.fromList(img.encodeJpg(image, quality: _jpegQuality));
  }
}
