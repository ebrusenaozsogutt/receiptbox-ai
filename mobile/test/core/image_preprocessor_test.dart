import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:receiptbox/core/ocr/image_preprocessor.dart';

Uint8List jpeg(int width, int height, {int? exifOrientation}) {
  final image = img.Image(width: width, height: height);
  img.fill(image, color: img.ColorRgb8(240, 240, 240));
  if (exifOrientation != null) {
    image.exif.imageIfd.orientation = exifOrientation;
  }
  return Uint8List.fromList(img.encodeJpg(image));
}

void main() {
  test('a big photo is scaled so that the long edge is 2000 px and the ratio stays', () {
    final out = img.decodeJpg(
      ImagePreprocessor.processBytes(jpeg(4000, 3000)),
    )!;
    expect(out.width, 2000);
    expect(out.height, 1500);
  });

  test('a tall receipt photo is limited on its height', () {
    final out = img.decodeJpg(
      ImagePreprocessor.processBytes(jpeg(1000, 5000)),
    )!;
    expect(out.height, 2000);
    expect(out.width, 400);
  });

  test('a small image is not scaled up', () {
    final out = img.decodeJpg(ImagePreprocessor.processBytes(jpeg(800, 600)))!;
    expect(out.width, 800);
    expect(out.height, 600);
  });

  test('the EXIF rotation is applied to the pixels and the tag is gone', () {
    // Orientation 6 = the phone was held sideways; the viewer must rotate 90 degrees.
    final out = img.decodeJpg(
      ImagePreprocessor.processBytes(jpeg(600, 300, exifOrientation: 6)),
    )!;
    expect(out.width, 300);
    expect(out.height, 600);
    expect(out.exif.imageIfd.orientation, anyOf(isNull, 1));
  });

  test('the output carries no EXIF data at all', () {
    final withExif = jpeg(100, 100, exifOrientation: 1);
    final out = img.decodeJpg(ImagePreprocessor.processBytes(withExif))!;
    expect(out.exif.isEmpty, isTrue);
  });

  test('bytes that are not an image are rejected', () {
    expect(
      () => ImagePreprocessor.processBytes(Uint8List.fromList([1, 2, 3, 4])),
      throwsA(isA<UnsupportedImageException>()),
    );
  });
}
