import 'dart:io';

import 'package:flutter/foundation.dart' show kDebugMode;

import '../../../core/ocr/capture_temp_dir.dart';
import '../../../core/ocr/image_preprocessor.dart';
import '../../../core/ocr/ocr_service.dart';
import '../../../core/ocr/pdf_page_renderer.dart';
import '../../../core/ocr/qr_service.dart';
import '../../../core/privacy/pii_masker.dart';
import '../domain/capture_payload.dart';

/// image / PDF -> [CaptureResult], entirely on the phone and offline:
///
///   (PDF: first 2 pages -> images) -> resize + upright -> QR -> OCR -> PII masking.
///
/// PRIVACY RULES of this class:
/// - the unmasked OCR text exists only inside [process]; it is masked right away and is not
///   stored, not sent and not logged (there is no logging in this file on purpose);
/// - [CaptureResult.debugOriginalText] is filled only when [keepOriginalForDebug] is true
///   (debug builds); in release builds the original text is dropped after masking;
/// - every image file created here (and the input copy) is deleted before [process] returns,
///   also when it fails.
class CapturePipeline {
  CapturePipeline({
    required this.ocr,
    required this.qr,
    required this.pdf,
    required this.tempDir,
    this.preprocessor = const ImagePreprocessor(),
    this.masker = const PiiMasker(),
    bool? keepOriginalForDebug,
  }) : keepOriginalForDebug = keepOriginalForDebug ?? kDebugMode;

  final OcrService ocr;
  final QrService qr;
  final PdfPageRenderer pdf;
  final CaptureTempDir tempDir;
  final ImagePreprocessor preprocessor;
  final PiiMasker masker;
  final bool keepOriginalForDebug;

  static const maxPdfPages = 2;

  Future<CaptureResult> process(CaptureInput input) async {
    final createdFiles = <File>[];
    File? retained;
    var succeeded = false;
    try {
      final temp = await tempDir.ensure();

      final List<File> pages;
      if (input.isPdf) {
        try {
          pages = await pdf.renderFirstPages(
            input.file,
            temp,
            maxPages: maxPdfPages,
          );
        } on Object {
          throw const CaptureException(CaptureFailure.unsupportedFile);
        }
        createdFiles.addAll(pages);
        if (pages.isEmpty) {
          throw const CaptureException(CaptureFailure.unsupportedFile);
        }
      } else {
        pages = [input.file];
      }

      Map<String, dynamic>? qrPayload;
      File? firstPrepared;
      final pageTexts = <String>[];
      for (final page in pages) {
        final File prepared;
        try {
          prepared = await preprocessor.prepare(page, temp);
        } on UnsupportedImageException {
          throw const CaptureException(CaptureFailure.unsupportedFile);
        }
        createdFiles.add(prepared);
        firstPrepared ??= prepared;

        try {
          qrPayload ??= await qr.findGibPayload(prepared.path);
          pageTexts.add(await ocr.readText(prepared.path));
        } on Object {
          throw const CaptureException(CaptureFailure.readFailed);
        }
      }

      final original = pageTexts
          .where((text) => text.trim().isNotEmpty)
          .join('\n\n');
      if (original.isEmpty && qrPayload == null) {
        throw const CaptureException(CaptureFailure.noTextFound);
      }

      final masked = masker.mask(original);
      // A bank screenshot is NEVER kept (spec 15.3, invariant 8), whatever the caller asked.
      if (input.keepImage && input.kind == CaptureKind.receipt) {
        retained = await _keepCopy(input, firstPrepared!, temp);
      }
      succeeded = true;
      return CaptureResult(
        payload: CapturePayload(
          kind: input.kind,
          maskedText: masked.text,
          qrPayload: qrPayload,
          captureDate: input.captureDate,
          source: input.source,
        ),
        maskedCounts: masked.counts,
        pageCount: pages.length,
        debugOriginalText: keepOriginalForDebug ? original : null,
        retainedImage: retained,
      );
    } finally {
      if (!succeeded && retained != null) await _deleteQuietly(retained);
      for (final file in createdFiles) {
        await _deleteQuietly(file);
      }
      if (input.deleteInput) await _deleteQuietly(input.file);
    }
  }

  /// The copy that outlives [process]: a PDF as it is, a photo as the clean prepared JPEG.
  Future<File> _keepCopy(CaptureInput input, File prepared, Directory temp) {
    final extension = input.isPdf ? 'pdf' : 'jpg';
    final target =
        '${temp.path}${Platform.pathSeparator}keep_${DateTime.now().microsecondsSinceEpoch}.$extension';
    return (input.isPdf ? input.file : prepared).copy(target);
  }

  Future<void> _deleteQuietly(File file) async {
    try {
      if (await file.exists()) await file.delete();
    } on FileSystemException {
      // Nothing more can be done; the folder is cleared at the next start.
    }
  }
}
