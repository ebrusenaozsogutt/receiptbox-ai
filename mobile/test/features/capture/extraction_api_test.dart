import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/core/networking/api_error.dart';
import 'package:receiptbox/features/capture/data/extraction_api.dart';
import 'package:receiptbox/features/capture/domain/capture_payload.dart';

/// A fake network: records what was sent and answers with [reply].
class _Adapter implements HttpClientAdapter {
  _Adapter(this.reply);

  final ResponseBody Function(RequestOptions options) reply;
  final requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    return reply(options);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody _json(
  int status,
  Object body, {
  Map<String, List<String>>? headers,
}) => ResponseBody.fromString(
  jsonEncode(body),
  status,
  headers: {
    Headers.contentTypeHeader: [Headers.jsonContentType],
    ...?headers,
  },
);

Map<String, Object> _answer({String ettn = 'obs-1', bool? aiUsed}) => {
  'observation_id': ettn,
  'extraction': {
    'merchant_raw': 'ORNEK ELEKTRONIK',
    'date': '2026-11-14',
    'time': null,
    'total': '2499.00',
    'currency': 'TRY',
    'payment_method': 'UNKNOWN',
    'installment_count': null,
    'items': [
      {
        'name_raw': 'KULAKLIK',
        'quantity': null,
        'unit_price': null,
        'total_price': '2499.00',
      },
    ],
  },
  'confidence': {'merchant': 'HIGH', 'date': 'HIGH', 'total': 'HIGH'},
  'suggestions': {
    'merchant': {
      'match': 'NEW',
      'merchant_id': null,
      'canonical_name': 'Ornek Elektronik',
      'score': null,
    },
    'category': {'key': 'TECHNOLOGY', 'source': 'LLM'},
  },
  'ai_used': ?aiUsed,
};

CapturePayload _payload({
  Map<String, dynamic>? qr,
  CaptureKind kind = CaptureKind.receipt,
  String text = 'ORNEK ELEKTRONIK\nTOPLAM 2.499,00',
}) => CapturePayload(
  kind: kind,
  maskedText: text,
  qrPayload: qr,
  captureDate: DateTime(2026, 11, 18),
  source: CaptureSource.gallery,
);

const _qr = {
  'ettn': '11111111-2222-3333-4444-555555555555',
  'odenecek': '2499.00',
};

({DioExtractionApi api, _Adapter adapter}) _rig(
  ResponseBody Function(RequestOptions) reply,
) {
  final adapter = _Adapter(reply);
  final dio = Dio(BaseOptions(baseUrl: 'http://test/api/v1'))
    ..httpClientAdapter = adapter;
  return (api: DioExtractionApi(dio), adapter: adapter);
}

void main() {
  group('which endpoint', () {
    test('a receipt text goes to /extract/receipt with the source', () async {
      final rig = _rig((_) => _json(200, _answer()));

      final result = await rig.api.extract(_payload(), aiConsent: true);

      final request = rig.adapter.requests.single;
      expect(request.path, '/extract/receipt');
      expect(request.data, {
        'masked_text': 'ORNEK ELEKTRONIK\nTOPLAM 2.499,00',
        'capture_date': '2026-11-18',
        'source': 'GALLERY',
      });
      expect(result.usedQr, isFalse);
      expect(result.total, '2499.00');
      expect(result.itemCount, 1);
      expect(result.merchantName, 'Ornek Elektronik');
      expect(result.categoryKey, 'TECHNOLOGY');
      expect(result.categorySource, 'LLM');
      expect(result.confidence['total'], 'HIGH');
    });

    test(
      'a GİB QR goes to /extract/einvoice-qr instead (phase item 6)',
      () async {
        final rig = _rig((_) => _json(200, _answer(aiUsed: true)));

        final result = await rig.api.extract(
          _payload(qr: _qr),
          aiConsent: true,
        );

        final request = rig.adapter.requests.single;
        expect(request.path, '/extract/einvoice-qr');
        expect(request.data['qr_payload'], _qr);
        expect(request.data['masked_text'], contains('TOPLAM'));
        expect(request.data['capture_date'], '2026-11-18');
        expect(request.data.containsKey('source'), isFalse);
        expect(result.usedQr, isTrue);
        expect(result.aiUsed, isTrue);
      },
    );
  });

  group('AI consent (spec 15.3)', () {
    test('a receipt text is never sent without consent', () async {
      final rig = _rig((_) => _json(200, _answer()));

      await expectLater(
        rig.api.extract(_payload(), aiConsent: false),
        throwsA(isA<AiConsentOffException>()),
      );

      expect(rig.adapter.requests, isEmpty);
    });

    test('a QR is still sent without consent, but without the text', () async {
      final rig = _rig((_) => _json(200, _answer(aiUsed: false)));

      final result = await rig.api.extract(_payload(qr: _qr), aiConsent: false);

      final request = rig.adapter.requests.single;
      expect(request.path, '/extract/einvoice-qr');
      expect(request.data.containsKey('masked_text'), isFalse);
      expect(result.aiUsed, isFalse);
    });

    test('an empty text is not sent with a QR either', () async {
      final rig = _rig((_) => _json(200, _answer()));

      await rig.api.extract(_payload(qr: _qr, text: '  '), aiConsent: true);

      expect(
        rig.adapter.requests.single.data.containsKey('masked_text'),
        isFalse,
      );
    });
  });

  test('bank screenshots are not handled yet (P08)', () async {
    final rig = _rig((_) => _json(200, _answer()));

    await expectLater(
      rig.api.extract(
        _payload(kind: CaptureKind.bankScreenshot),
        aiConsent: true,
      ),
      throwsA(isA<ExtractionNotAvailableException>()),
    );
    expect(rig.adapter.requests, isEmpty);
  });

  test('a model call may take longer than the usual 10 seconds', () async {
    final rig = _rig((_) => _json(200, _answer()));

    await rig.api.extract(_payload(), aiConsent: true);

    expect(
      rig.adapter.requests.single.receiveTimeout,
      const Duration(seconds: 45),
    );
  });

  group('errors become Turkish messages', () {
    for (final entry in {
      'AI_CONSENT_REQUIRED': 'Yapay zekâ ile okuma kapalı',
      'EXTRACTION_FAILED': 'Fiş şu an okunamadı',
      'EXTRACTION_REJECTED': 'güvenilir okunamadı',
      'QR_INVALID': 'QR kodu okunabilir',
      'TEXT_TOO_LARGE': 'Metin çok uzun',
    }.entries) {
      test(entry.key, () async {
        final rig = _rig(
          (_) => _json(422, {
            'error': {'code': entry.key, 'message': 'x'},
          }),
        );

        await expectLater(
          rig.api.extract(_payload(), aiConsent: true),
          throwsA(
            isA<ApiError>()
                .having((e) => e.code, 'code', entry.key)
                .having((e) => e.message, 'message', contains(entry.value)),
          ),
        );
      });
    }

    test('a 429 tells how long to wait', () async {
      final rig = _rig(
        (_) => _json(
          429,
          {
            'error': {'code': 'RATE_LIMITED', 'message': 'x'},
          },
          headers: {
            'retry-after': ['12'],
          },
        ),
      );

      await expectLater(
        rig.api.extract(_payload(), aiConsent: true),
        throwsA(
          isA<ApiError>().having(
            (e) => e.message,
            'message',
            contains('12 saniye'),
          ),
        ),
      );
    });
  });
}
