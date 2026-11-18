import 'dart:io';

import 'package:pdfx/pdfx.dart';

/// Turns the first pages of a PDF into image files.
abstract interface class PdfPageRenderer {
  Future<List<File>> renderFirstPages(
    File pdf,
    Directory outputDirectory, {
    int maxPages,
  });
}

/// pdfx (the platform's own PDF renderer). Pages are drawn on a white background with the long
/// edge at about [targetLongEdge] pixels. The caller owns the files and must delete them.
class PdfxPageRenderer implements PdfPageRenderer {
  const PdfxPageRenderer();

  static const targetLongEdge = 2000.0;

  @override
  Future<List<File>> renderFirstPages(
    File pdf,
    Directory outputDirectory, {
    int maxPages = 2,
  }) async {
    final document = await PdfDocument.openFile(pdf.path);
    final files = <File>[];
    try {
      final count = document.pagesCount < maxPages
          ? document.pagesCount
          : maxPages;
      for (var number = 1; number <= count; number++) {
        final page = await document.getPage(number);
        try {
          final scale =
              targetLongEdge /
              (page.width > page.height ? page.width : page.height);
          final image = await page.render(
            width: page.width * scale,
            height: page.height * scale,
            format: PdfPageImageFormat.jpeg,
            backgroundColor: '#FFFFFF',
            quality: 90,
          );
          if (image == null) continue;
          final file = File(
            '${outputDirectory.path}${Platform.pathSeparator}pdf_${DateTime.now().microsecondsSinceEpoch}_$number.jpg',
          );
          await file.writeAsBytes(image.bytes, flush: true);
          files.add(file);
        } finally {
          await page.close(); // pdfx renders one page at a time
        }
      }
    } finally {
      await document.close();
    }
    return files;
  }
}
