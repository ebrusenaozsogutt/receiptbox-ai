import 'package:google_mlkit_barcode_scanning/google_mlkit_barcode_scanning.dart';

import 'gib_qr_parser.dart';

/// Reads the raw text of every QR code in an image file.
abstract interface class QrScanEngine {
  Future<List<String>> scan(String imagePath);
  Future<void> close();
}

/// ML Kit barcode scanning (QR only), on the device.
class MlKitQrScanEngine implements QrScanEngine {
  MlKitQrScanEngine()
    : _scanner = BarcodeScanner(formats: [BarcodeFormat.qrCode]);

  final BarcodeScanner _scanner;

  @override
  Future<List<String>> scan(String imagePath) async {
    final barcodes = await _scanner.processImage(
      InputImage.fromFilePath(imagePath),
    );
    return [
      for (final barcode in barcodes)
        if (barcode.rawValue != null) barcode.rawValue!,
    ];
  }

  @override
  Future<void> close() => _scanner.close();
}

/// Image file -> the cleaned payload of a GİB e-invoice QR, or null.
///
/// Only a GİB invoice QR is ever returned (and without the buyer's identity number, see
/// [GibQrParser]); the content of any other QR code is dropped right here.
class QrService {
  const QrService(this._engine, [this._parser = const GibQrParser()]);

  final QrScanEngine _engine;
  final GibQrParser _parser;

  Future<Map<String, dynamic>?> findGibPayload(String imagePath) async {
    return _parser.firstGibPayload(await _engine.scan(imagePath));
  }
}
