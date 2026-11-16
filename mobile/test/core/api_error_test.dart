import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/core/networking/api_error.dart';

DioException _httpError(
  int status, {
  Object? body,
  Map<String, List<String>> headers = const {},
}) {
  final options = RequestOptions(path: '/x');
  return DioException(
    requestOptions: options,
    response: Response<Object?>(
      requestOptions: options,
      statusCode: status,
      data: body,
      headers: Headers.fromMap(headers),
    ),
    type: DioExceptionType.badResponse,
  );
}

Map<String, Object> _body(String code) => {
  'error': {'code': code, 'message': 'English text from the server'},
};

void main() {
  group('backend error codes -> Turkish messages (one place)', () {
    const expectations = {
      'AUTH_INVALID_CREDENTIALS': 'E-posta veya parola hatalı.',
      'AUTH_EXPIRED': 'Oturum süren doldu. Lütfen tekrar giriş yap.',
      'AUTH_INVALID_TOKEN': 'Oturumun geçersiz. Lütfen tekrar giriş yap.',
      'EMAIL_ALREADY_REGISTERED':
          'Bu e-posta adresiyle zaten bir hesap var. Giriş yapmayı dene.',
      'INVALID_EMAIL': 'Geçerli bir e-posta adresi gir.',
      'ADULT_CONFIRMATION_REQUIRED':
          'Devam etmek için 18 yaşından büyük olduğunu onaylamalısın.',
      'VALIDATION_ERROR':
          'Girdiğin bilgiler geçersiz. Kontrol edip tekrar dene.',
      'NOT_FOUND': 'İstenen kayıt bulunamadı.',
      'INTERNAL_ERROR': 'Sunucuda bir sorun oluştu. Biraz sonra tekrar dene.',
    };
    for (final entry in expectations.entries) {
      test(entry.key, () {
        final error = apiErrorFrom(_httpError(400, body: _body(entry.key)));

        expect(error.code, entry.key);
        expect(error.message, entry.value);
      });
    }

    test('WEAK_PASSWORD explains the rules', () {
      expect(messageForCode('WEAK_PASSWORD'), contains('8-128 karakter'));
    });

    test(
      'an unknown code gets a generic Turkish message, never the server text',
      () {
        final error = apiErrorFrom(
          _httpError(418, body: _body('SOMETHING_NEW')),
        );

        expect(error.code, 'SOMETHING_NEW');
        expect(error.message, 'Bir şeyler ters gitti. Tekrar dene.');
      },
    );
  });

  group('rate limit', () {
    test('uses the Retry-After header', () {
      final error = apiErrorFrom(
        _httpError(
          429,
          body: _body('RATE_LIMITED'),
          headers: {
            'retry-after': ['42'],
          },
        ),
      );

      expect(error.retryAfterSeconds, 42);
      expect(
        error.message,
        'Çok fazla deneme yaptın. 42 saniye sonra tekrar dene.',
      );
    });

    test('works without the header', () {
      final error = apiErrorFrom(_httpError(429, body: _body('RATE_LIMITED')));

      expect(
        error.message,
        'Çok fazla deneme yaptın. Biraz bekleyip tekrar dene.',
      );
    });
  });

  group('connection problems', () {
    test('no connection', () {
      final error = apiErrorFrom(
        DioException.connectionError(
          requestOptions: RequestOptions(),
          reason: 'x',
        ),
      );

      expect(error.code, 'NETWORK_UNREACHABLE');
      expect(
        error.message,
        'Sunucuya ulaşılamıyor. İnternet bağlantını kontrol et.',
      );
      expect(error.statusCode, isNull);
    });

    test('timeouts', () {
      for (final type in [
        DioExceptionType.connectionTimeout,
        DioExceptionType.sendTimeout,
        DioExceptionType.receiveTimeout,
      ]) {
        final error = apiErrorFrom(
          DioException(requestOptions: RequestOptions(), type: type),
        );
        expect(error.code, 'NETWORK_TIMEOUT', reason: '$type');
      }
    });
  });

  group('other cases', () {
    test('a 5xx without a JSON body is INTERNAL_ERROR', () {
      final error = apiErrorFrom(
        _httpError(502, body: '<html>Bad gateway</html>'),
      );

      expect(error.code, 'INTERNAL_ERROR');
      expect(error.statusCode, 502);
    });

    test('isUnauthorized is true only for 401', () {
      expect(
        apiErrorFrom(_httpError(401, body: _body('AUTH_EXPIRED')))
            .isUnauthorized,
        isTrue,
      );
      expect(
        apiErrorFrom(_httpError(403, body: _body('X'))).isUnauthorized,
        isFalse,
      );
    });

    test('an ApiError passes through unchanged', () {
      const original = ApiError(code: 'X', message: 'm', statusCode: 400);

      expect(identical(apiErrorFrom(original), original), isTrue);
    });

    test('a non-Dio exception becomes UNKNOWN', () {
      expect(apiErrorFrom(StateError('boom')).code, 'UNKNOWN');
    });
  });
}
