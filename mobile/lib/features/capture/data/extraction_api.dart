import 'package:dio/dio.dart';

import '../../../core/networking/api_error.dart';
import '../domain/capture_payload.dart';
import '../domain/extraction_result.dart';

/// The user has not agreed that masked text goes to an external AI provider (spec 15.3), so a
/// receipt text must not be sent. (A GİB QR can still be sent: it is read without any AI.)
class AiConsentOffException implements Exception {
  const AiConsentOffException();

  String get message =>
      'Yapay zekâ ile okuma kapalı. Ayarlar\'dan açabilirsin; '
      'şimdilik fişi elle ekleyebilirsin.';
}

/// Bank screenshots are handled in a later phase (P08).
class ExtractionNotAvailableException implements Exception {
  const ExtractionNotAvailableException();

  String get message => 'Banka ekran görüntüleri sonraki aşamada eklenecek.';
}

/// Sends a [CapturePayload] to the right extraction endpoint:
/// a GİB QR (`qrPayload`) goes to `/extract/einvoice-qr`, anything else to `/extract/receipt`.
abstract interface class ExtractionApi {
  /// [aiConsent] is the user's local choice. Throws [AiConsentOffException],
  /// [ExtractionNotAvailableException] or an [ApiError] with a Turkish message.
  Future<ExtractionResult> extract(
    CapturePayload payload, {
    required bool aiConsent,
  });
}

class DioExtractionApi implements ExtractionApi {
  const DioExtractionApi(this._dio);

  final Dio _dio;

  /// A model call can take up to 30 s on the server (retries included).
  static const _receiveTimeout = Duration(seconds: 45);

  @override
  Future<ExtractionResult> extract(
    CapturePayload payload, {
    required bool aiConsent,
  }) async {
    if (payload.kind == CaptureKind.bankScreenshot) {
      throw const ExtractionNotAvailableException();
    }
    final usesQr = payload.qrPayload != null;
    if (!usesQr && !aiConsent) throw const AiConsentOffException();

    final date = payload.captureDate.toIso8601String().substring(0, 10);
    final Map<String, dynamic> body;
    if (usesQr) {
      body = {
        'qr_payload': payload.qrPayload,
        // The text is only sent when the user agreed to AI reading.
        if (aiConsent && payload.maskedText.trim().isNotEmpty)
          'masked_text': payload.maskedText,
        'capture_date': date,
      };
    } else {
      body = {
        'masked_text': payload.maskedText,
        'capture_date': date,
        'source': payload.source.wireName,
      };
    }

    try {
      final response = await _dio.post<Map<String, dynamic>>(
        usesQr ? '/extract/einvoice-qr' : '/extract/receipt',
        data: body,
        options: Options(receiveTimeout: _receiveTimeout),
      );
      return ExtractionResult.fromJson(response.data!, usedQr: usesQr);
    } on Object catch (error) {
      throw apiErrorFrom(error);
    }
  }
}
