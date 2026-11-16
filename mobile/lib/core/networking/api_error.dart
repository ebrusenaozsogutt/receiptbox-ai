import 'package:dio/dio.dart';

/// A backend (or connection) error with a Turkish message for the user.
///
/// Every backend error code is mapped to its message in [messageForCode], the single place
/// where this happens. The backend codes are listed in backend/app/core/errors.py.
class ApiError implements Exception {
  const ApiError({
    required this.code,
    required this.message,
    this.statusCode,
    this.retryAfterSeconds,
  });

  /// Backend code such as "AUTH_INVALID_CREDENTIALS", or a client-side one
  /// ("NETWORK_UNREACHABLE", "NETWORK_TIMEOUT", "UNKNOWN").
  final String code;

  /// Turkish text that can be shown to the user as is.
  final String message;
  final int? statusCode;
  final int? retryAfterSeconds;

  bool get isUnauthorized => statusCode == 401;

  @override
  String toString() => 'ApiError($code, status: $statusCode)';
}

/// The Turkish message for an error code. [retryAfterSeconds] is used by RATE_LIMITED.
String messageForCode(String code, {int? retryAfterSeconds}) {
  switch (code) {
    case 'AUTH_INVALID_CREDENTIALS':
      return 'E-posta veya parola hatalı.';
    case 'AUTH_EXPIRED':
      return 'Oturum süren doldu. Lütfen tekrar giriş yap.';
    case 'AUTH_INVALID_TOKEN':
      return 'Oturumun geçersiz. Lütfen tekrar giriş yap.';
    case 'EMAIL_ALREADY_REGISTERED':
      return 'Bu e-posta adresiyle zaten bir hesap var. Giriş yapmayı dene.';
    case 'INVALID_EMAIL':
      return 'Geçerli bir e-posta adresi gir.';
    case 'WEAK_PASSWORD':
      return 'Parola 8-128 karakter olmalı ve en az bir harf ile bir rakam içermeli.';
    case 'ADULT_CONFIRMATION_REQUIRED':
      return 'Devam etmek için 18 yaşından büyük olduğunu onaylamalısın.';
    case 'RATE_LIMITED':
      return retryAfterSeconds == null
          ? 'Çok fazla deneme yaptın. Biraz bekleyip tekrar dene.'
          : 'Çok fazla deneme yaptın. $retryAfterSeconds saniye sonra tekrar dene.';
    case 'VALIDATION_ERROR':
      return 'Girdiğin bilgiler geçersiz. Kontrol edip tekrar dene.';
    case 'NOT_FOUND':
      return 'İstenen kayıt bulunamadı.';
    case 'INTERNAL_ERROR':
      return 'Sunucuda bir sorun oluştu. Biraz sonra tekrar dene.';
    case 'NETWORK_UNREACHABLE':
      return 'Sunucuya ulaşılamıyor. İnternet bağlantını kontrol et.';
    case 'NETWORK_TIMEOUT':
      return 'Sunucu zamanında yanıt vermedi. Tekrar dene.';
    default:
      return 'Bir şeyler ters gitti. Tekrar dene.';
  }
}

/// Turns anything thrown by a request into an [ApiError].
ApiError apiErrorFrom(Object error) {
  if (error is ApiError) return error;
  if (error is! DioException) {
    return ApiError(code: 'UNKNOWN', message: messageForCode('UNKNOWN'));
  }

  final response = error.response;
  if (response != null) {
    final retryAfter = int.tryParse(
      response.headers.value('retry-after') ?? '',
    );
    final data = response.data;
    var code = 'UNKNOWN';
    if (data is Map && data['error'] is Map) {
      code = (data['error'] as Map)['code'] as String? ?? 'UNKNOWN';
    } else if (response.statusCode != null && response.statusCode! >= 500) {
      code = 'INTERNAL_ERROR';
    }
    return ApiError(
      code: code,
      message: messageForCode(code, retryAfterSeconds: retryAfter),
      statusCode: response.statusCode,
      retryAfterSeconds: retryAfter,
    );
  }

  switch (error.type) {
    case DioExceptionType.connectionTimeout:
    case DioExceptionType.sendTimeout:
    case DioExceptionType.receiveTimeout:
      return ApiError(
        code: 'NETWORK_TIMEOUT',
        message: messageForCode('NETWORK_TIMEOUT'),
      );
    default:
      return ApiError(
        code: 'NETWORK_UNREACHABLE',
        message: messageForCode('NETWORK_UNREACHABLE'),
      );
  }
}
