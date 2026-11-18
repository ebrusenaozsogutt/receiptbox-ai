import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';

import 'reading_order.dart';

/// Finds the text lines (with positions) in an image file.
abstract interface class TextRecognitionEngine {
  Future<List<OcrLine>> recognize(String imagePath);
  Future<void> close();
}

/// ML Kit text recognition, Latin script, running ON THE DEVICE (no network, no Google call).
class MlKitTextRecognitionEngine implements TextRecognitionEngine {
  MlKitTextRecognitionEngine()
    : _recognizer = TextRecognizer(script: TextRecognitionScript.latin);

  final TextRecognizer _recognizer;

  @override
  Future<List<OcrLine>> recognize(String imagePath) async {
    final result = await _recognizer.processImage(
      InputImage.fromFilePath(imagePath),
    );
    return [
      for (final block in result.blocks)
        for (final line in block.lines)
          OcrLine(
            text: line.text,
            left: line.boundingBox.left,
            top: line.boundingBox.top,
            right: line.boundingBox.right,
            bottom: line.boundingBox.bottom,
          ),
    ];
  }

  @override
  Future<void> close() => _recognizer.close();
}

/// Image file -> text in reading order. The returned text is UNMASKED: the caller (the capture
/// pipeline) masks it immediately and must never store or log it.
class OcrService {
  const OcrService(this._engine, [this._readingOrder = const ReadingOrder()]);

  final TextRecognitionEngine _engine;
  final ReadingOrder _readingOrder;

  Future<String> readText(String imagePath) async {
    return _readingOrder.arrange(await _engine.recognize(imagePath));
  }
}
