import 'dart:io';

import '../../../core/privacy/pii_masker.dart';

/// What the user is capturing. Camera is always a receipt; gallery and share ask.
enum CaptureKind {
  receipt('RECEIPT'),
  bankScreenshot('BANK_SCREENSHOT');

  const CaptureKind(this.wireName);

  /// The value the backend API expects.
  final String wireName;
}

enum CaptureSource {
  camera('CAMERA'),
  gallery('GALLERY'),
  share('SHARE');

  const CaptureSource(this.wireName);

  final String wireName;
}

/// Everything the phone learned from one capture, ready to be sent to the backend in P05.
///
/// Holds MASKED text only. The original OCR text never ends up in here.
class CapturePayload {
  const CapturePayload({
    required this.kind,
    required this.maskedText,
    required this.captureDate,
    required this.source,
    this.qrPayload,
  });

  final CaptureKind kind;
  final String maskedText;

  /// The cleaned GİB e-invoice QR content (no buyer TCKN), when the image had one.
  final Map<String, dynamic>? qrPayload;

  /// Device date for the camera; for gallery/share the file's last-modified time if known.
  final DateTime captureDate;
  final CaptureSource source;

  Map<String, dynamic> toJson() => {
    'kind': kind.wireName,
    'masked_text': maskedText,
    if (qrPayload != null) 'qr_payload': qrPayload,
    'capture_date': captureDate.toIso8601String().substring(0, 10),
    'source': source.wireName,
  };
}

/// A payload plus what the screens need to show about it.
class CaptureResult {
  const CaptureResult({
    required this.payload,
    required this.maskedCounts,
    required this.pageCount,
    this.debugOriginalText,
    this.retainedImage,
  });

  final CapturePayload payload;

  /// How many items of each kind were masked (counts only, never the values).
  final Map<PiiType, int> maskedCounts;
  final int pageCount;

  /// The UNMASKED OCR text. Only set in debug builds, so that the owner can compare it with
  /// the masked text on the debug screen. Null in release builds: there the original text is
  /// not even kept in memory after masking. It is never written anywhere.
  final String? debugOriginalText;

  /// The image to keep as proof of purchase, only when the user keeps receipt images AND this
  /// is a receipt (never for a bank screenshot). A photo: the resized, upright copy WITHOUT EXIF
  /// data (no GPS location). A PDF: the original file. A private copy in the app's temporary
  /// folder: whoever receives the result must delete it (it is uploaded in P07 and then removed).
  final File? retainedImage;

  /// The same outcome without the kept image (for a screen that must not own the file).
  CaptureResult withoutRetainedImage() => CaptureResult(
    payload: payload,
    maskedCounts: maskedCounts,
    pageCount: pageCount,
    debugOriginalText: debugOriginalText,
  );

  bool get retainedIsPdf => retainedImage?.path.endsWith('.pdf') ?? false;

  int get maskedTotal =>
      maskedCounts.values.fold(0, (sum, count) => sum + count);
}

/// One file to process.
class CaptureInput {
  const CaptureInput({
    required this.file,
    required this.kind,
    required this.source,
    required this.captureDate,
    this.isPdf = false,
    this.deleteInput = true,
    this.keepImage = false,
  });

  final File file;
  final bool isPdf;
  final CaptureKind kind;
  final CaptureSource source;
  final DateTime captureDate;

  /// The file is a copy that belongs to the app (camera / picker / share cache): delete it
  /// when done. Images are not stored in P04 (that is P07).
  final bool deleteInput;

  /// Keep a clean copy of the image after reading (see [CaptureResult.retainedImage]). Ignored
  /// for bank screenshots, which are never kept.
  final bool keepImage;

  CaptureInput copyWith({bool? keepImage}) => CaptureInput(
    file: file,
    isPdf: isPdf,
    kind: kind,
    source: source,
    captureDate: captureDate,
    deleteInput: deleteInput,
    keepImage: keepImage ?? this.keepImage,
  );
}

enum CaptureFailure { noTextFound, unsupportedFile, readFailed }

class CaptureException implements Exception {
  const CaptureException(this.failure);

  final CaptureFailure failure;

  /// Turkish text for the user. Never contains any text from the image.
  String get message => switch (failure) {
    CaptureFailure.noTextFound => 'Görüntüde okunabilir yazı bulunamadı. Daha net ve iyi aydınlatılmış bir görüntü dene.',
    CaptureFailure.unsupportedFile =>
      'Bu dosya okunamadı. Fotoğraf (JPG, PNG) veya PDF seçmelisin.',
    CaptureFailure.readFailed =>
      'Görüntü okunurken bir sorun oluştu. Tekrar dene.',
  };

  @override
  String toString() => 'CaptureException($failure)';
}
