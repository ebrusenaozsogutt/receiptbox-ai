import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/core/networking/dio_provider.dart';
import 'package:receiptbox/core/theme/app_theme.dart';
import 'package:receiptbox/features/health/data/health_repository.dart';
import 'package:receiptbox/features/health/domain/health_status.dart';
import 'package:receiptbox/features/health/presentation/server_status_tile.dart';
import 'package:dio/dio.dart';

import 'dart:convert';
import 'dart:typed_data';

/// Answers `GET /health` with a fixed response, or with a connection error.
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

/// The real repository + provider + tile, with only the network faked.
Future<void> _pump(WidgetTester tester, HttpClientAdapter adapter) async {
  final dio = Dio(BaseOptions(baseUrl: 'http://test/api/v1'))
    ..httpClientAdapter = adapter;
  await tester.pumpWidget(
    ProviderScope(
      overrides: [publicDioProvider.overrideWithValue(dio)],
      child: MaterialApp(
        theme: AppTheme.light(),
        home: const Scaffold(body: ServerStatusTile()),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows "Sunucu: bağlı" when the API and database are ok', (
    tester,
  ) async {
    await _pump(tester, _FakeAdapter.json(200, {'status': 'ok', 'db': 'ok'}));

    expect(find.text('Sunucu: bağlı'), findsOneWidget);
  });

  testWidgets('shows a database error when the API answers 503', (
    tester,
  ) async {
    await _pump(
      tester,
      _FakeAdapter.json(503, {'status': 'degraded', 'db': 'error'}),
    );

    expect(find.text('Sunucu: veritabanı hatası'), findsOneWidget);
  });

  testWidgets('shows "Sunucu: bağlantı yok" when the server is unreachable', (
    tester,
  ) async {
    await _pump(tester, _FakeAdapter.unreachable());

    expect(find.text('Sunucu: bağlantı yok'), findsOneWidget);
  });

  testWidgets('"Tekrar dene" asks again', (tester) async {
    var calls = 0;
    final container = ProviderContainer(
      overrides: [
        healthStatusProvider.overrideWith((ref) async {
          calls++;
          return const HealthStatus(status: 'ok', db: 'ok');
        }),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(body: ServerStatusTile()),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(calls, 1);

    await tester.tap(find.text('Tekrar dene'));
    await tester.pumpAndSettle();

    expect(calls, 2);
  });
}
