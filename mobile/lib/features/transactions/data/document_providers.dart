import 'dart:typed_data';

import 'package:pdfx/pdfx.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../domain/purchase_models.dart';
import 'transactions_api.dart';

part 'document_providers.g.dart';

/// The bytes of a stored document, fetched with a short-lived access token. An image shows as
/// they are; for a PDF these are the PDF bytes (see [documentPreview]).
@riverpod
Future<Uint8List> documentBytes(Ref ref, String documentId) =>
    ref.watch(documentsApiProvider).content(documentId);

/// Something an `Image.memory` can show: the image itself, or the first page of a PDF.
@riverpod
Future<Uint8List> documentPreview(Ref ref, DocumentInfo document) async {
  final bytes = await ref.watch(documentBytesProvider(document.id).future);
  if (!document.isPdf) return bytes;
  final pdf = await PdfDocument.openData(bytes);
  try {
    final page = await pdf.getPage(1);
    try {
      final image = await page.render(
        width: page.width * 2,
        height: page.height * 2,
        format: PdfPageImageFormat.png,
        backgroundColor: '#FFFFFF',
      );
      if (image == null) throw StateError('the PDF page could not be drawn');
      return image.bytes;
    } finally {
      await page.close();
    }
  } finally {
    await pdf.close();
  }
}
