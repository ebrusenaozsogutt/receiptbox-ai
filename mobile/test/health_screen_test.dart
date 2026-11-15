import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/app.dart';
import 'package:receiptbox/core/networking/dio_provider.dart';

/// A Dio adapter that answers with a fixed response (or a connection error),
/// so the test exercises the real repository + provider + screen without a network.
class _FakeAdapter implements HttpClientAdapter {
  _FakeAdapter.json(int status, Map<String, Object> body)
    : _status = status,
      _body = jsonEncode(body);

  _FakeAdapter.unreachable() : _status = null, _body = null;

  final int? _status;
  final String? _body;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    if (_status == null) {
      throw DioException.connectionError(
        requestOptions: options,
        reason: 'unreachable (test)',
      );
    }
    return ResponseBody.fromString(
      _body!,
      _status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

Future<void> _pumpApp(WidgetTester tester, HttpClientAdapter adapter) async {
  final dio = Dio(
    BaseOptions(
      baseUrl: 'http://test/api/v1',
      validateStatus: (s) => s == 200 || s == 503,
    ),
  )..httpClientAdapter = adapter;

  await tester.pumpWidget(
    ProviderScope(
      overrides: [dioProvider.overrideWithValue(dio)],
      child: const ReceiptBoxApp(),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows "Sunucu: bağlı" when the API and database are ok', (
    tester,
  ) async {
    await _pumpApp(
      tester,
      _FakeAdapter.json(200, {'status': 'ok', 'db': 'ok'}),
    );

    expect(find.text('Sunucu: bağlı'), findsOneWidget);
  });

  testWidgets('shows a database error when the API answers 503', (
    tester,
  ) async {
    await _pumpApp(
      tester,
      _FakeAdapter.json(503, {'status': 'degraded', 'db': 'error'}),
    );

    expect(find.text('Sunucu: veritabanı hatası'), findsOneWidget);
  });

  testWidgets('shows "Sunucu: bağlantı yok" when the server is unreachable', (
    tester,
  ) async {
    await _pumpApp(tester, _FakeAdapter.unreachable());

    expect(find.text('Sunucu: bağlantı yok'), findsOneWidget);
  });
}
