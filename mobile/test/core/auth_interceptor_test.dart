import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/core/networking/auth_interceptor.dart';
import 'package:receiptbox/core/storage/token_store.dart';

import '../support/fakes.dart';

/// What the scripted server saw.
class _Seen {
  _Seen(this.method, this.path, this.authorization);
  final String method;
  final String path;
  final String? authorization;
  @override
  String toString() => '$method $path [$authorization]';
}

/// A fake network: every request goes to [onRequest], which answers (or throws).
class _ScriptedAdapter implements HttpClientAdapter {
  _ScriptedAdapter(this.onRequest);

  final Future<ResponseBody> Function(RequestOptions options) onRequest;
  final seen = <_Seen>[];

  int count(String path) => seen.where((s) => s.path == path).length;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) {
    seen.add(
      _Seen(
        options.method,
        options.path,
        options.headers['Authorization'] as String?,
      ),
    );
    return onRequest(options);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody _json(int status, Object body) => ResponseBody.fromString(
  jsonEncode(body),
  status,
  headers: {
    Headers.contentTypeHeader: [Headers.jsonContentType],
  },
);

ResponseBody _error(int status, String code) => _json(status, {
  'error': {'code': code, 'message': 'x'},
});

Map<String, Object> _tokens(String suffix) => {
  'access_token': 'access-$suffix',
  'refresh_token': 'refresh-$suffix',
  'token_type': 'bearer',
  'expires_in': 900,
};

class _Rig {
  _Rig(this.adapter, {AuthTokens? initial})
    : store = InMemoryTokenStore(
        initial ??
            const AuthTokens(
              accessToken: 'access-old',
              refreshToken: 'refresh-old',
            ),
      ) {
    // The real app uses two Dio objects: one WITH the interceptor and a plain one for refresh.
    final refreshDio = Dio(BaseOptions(baseUrl: 'http://test/api/v1'))
      ..httpClientAdapter = adapter;
    dio = Dio(BaseOptions(baseUrl: 'http://test/api/v1'))
      ..httpClientAdapter = adapter;
    final interceptor = AuthInterceptor(
      tokenStore: store,
      refreshDio: refreshDio,
      onSessionExpired: () => sessionExpiredCalls++,
    );
    dio.interceptors.add(interceptor);
    interceptor.attach(dio);
  }

  final _ScriptedAdapter adapter;
  final InMemoryTokenStore store;
  late final Dio dio;
  int sessionExpiredCalls = 0;
}

void main() {
  test('attaches the access token to requests', () async {
    final adapter = _ScriptedAdapter((_) async => _json(200, {'ok': true}));
    final rig = _Rig(adapter);

    await rig.dio.get<void>('/me');

    expect(adapter.seen.single.authorization, 'Bearer access-old');
  });

  test('sends no Authorization header when signed out', () async {
    final adapter = _ScriptedAdapter((_) async => _json(200, {'ok': true}));
    final rig = _Rig(adapter);
    await rig.store.clear();

    await rig.dio.get<void>('/health');

    expect(adapter.seen.single.authorization, isNull);
  });

  test(
    'on 401 it refreshes once, then retries the request with the new token',
    () async {
      final adapter = _ScriptedAdapter((options) async {
        if (options.path == '/auth/refresh') return _json(200, _tokens('new'));
        final isNewToken =
            options.headers['Authorization'] == 'Bearer access-new';
        return isNewToken
            ? _json(200, {'email': 'a@b.c'})
            : _error(401, 'AUTH_EXPIRED');
      });
      final rig = _Rig(adapter);

      final response = await rig.dio.get<Map<String, dynamic>>('/me');

      expect(response.data, {'email': 'a@b.c'});
      expect(adapter.seen.map((s) => '${s.method} ${s.path}'), [
        'GET /me',
        'POST /auth/refresh',
        'GET /me',
      ]);
      expect(adapter.seen.last.authorization, 'Bearer access-new');
      expect(
        (await rig.store.read())!.refreshToken,
        'refresh-new',
      ); // the rotated token is stored
      expect(rig.sessionExpiredCalls, 0);
    },
  );

  test('the refresh request carries the stored refresh token', () async {
    Object? sentBody;
    final adapter = _ScriptedAdapter((options) async {
      if (options.path == '/auth/refresh') {
        sentBody = options.data;
        return _json(200, _tokens('new'));
      }
      return options.headers['Authorization'] == 'Bearer access-new'
          ? _json(200, {})
          : _error(401, 'AUTH_EXPIRED');
    });

    await _Rig(adapter).dio.get<void>('/me');

    expect(sentBody, {'refresh_token': 'refresh-old'});
  });

  test('several requests failing together share ONE refresh', () async {
    final refreshGate = Completer<void>();
    final adapter = _ScriptedAdapter((options) async {
      if (options.path == '/auth/refresh') {
        await refreshGate
            .future; // keep the refresh "in flight" while the others fail
        return _json(200, _tokens('new'));
      }
      return options.headers['Authorization'] == 'Bearer access-new'
          ? _json(200, {'path': options.path})
          : _error(401, 'AUTH_EXPIRED');
    });
    final rig = _Rig(adapter);

    final all = Future.wait([
      rig.dio.get<void>('/a'),
      rig.dio.get<void>('/b'),
      rig.dio.get<void>('/c'),
    ]);
    await Future<void>.delayed(const Duration(milliseconds: 50));
    refreshGate.complete();
    final responses = await all;

    expect(responses.map((r) => r.statusCode), [200, 200, 200]);
    // A refresh token works only once: a second refresh would log the user out on the server.
    expect(adapter.count('/auth/refresh'), 1);
  });

  test(
    'a request that fails AFTER another one already refreshed just retries',
    () async {
      final slowFailure = Completer<ResponseBody>();
      final adapter = _ScriptedAdapter((options) async {
        if (options.path == '/auth/refresh') return _json(200, _tokens('new'));
        if (options.headers['Authorization'] == 'Bearer access-new') {
          return _json(200, {'path': options.path});
        }
        // The old token is rejected; /slow answers late.
        return options.path == '/slow'
            ? slowFailure.future
            : _error(401, 'AUTH_EXPIRED');
      });
      final rig = _Rig(adapter);

      final slow = rig.dio.get<void>(
        '/slow',
      ); // sent with the old token, answer pending
      await Future<void>.delayed(const Duration(milliseconds: 10));
      await rig.dio.get<void>('/fast'); // fails with 401, refreshes, succeeds
      expect(adapter.count('/auth/refresh'), 1);

      slowFailure.complete(
        _error(401, 'AUTH_EXPIRED'),
      ); // the old request's 401 arrives now
      final response = await slow;

      expect(response.statusCode, 200);
      expect(
        adapter.count('/auth/refresh'),
        1,
        reason: 'must not replay the used refresh token',
      );
    },
  );

  test('when the refresh is rejected the session ends: tokens deleted, callback runs', () async {
    final adapter = _ScriptedAdapter((options) async {
      return options.path == '/auth/refresh'
          ? _error(401, 'AUTH_INVALID_TOKEN')
          : _error(401, 'AUTH_EXPIRED');
    });
    final rig = _Rig(adapter);

    await expectLater(
      rig.dio.get<void>('/me'),
      throwsA(
        isA<DioException>().having(
          (e) => e.response?.statusCode,
          'status',
          401,
        ),
      ),
    );

    expect(await rig.store.read(), isNull);
    expect(rig.sessionExpiredCalls, 1);
    expect(
      adapter.count('/me'),
      1,
      reason: 'no retry after a rejected refresh',
    );
  });

  test('a bad network during refresh keeps the session and reports the network error', () async {
    final adapter = _ScriptedAdapter((options) async {
      if (options.path == '/auth/refresh') {
        throw DioException.connectionError(
          requestOptions: options,
          reason: 'offline',
        );
      }
      return _error(401, 'AUTH_EXPIRED');
    });
    final rig = _Rig(adapter);

    await expectLater(
      rig.dio.get<void>('/me'),
      throwsA(
        isA<DioException>()
            .having((e) => e.type, 'type', DioExceptionType.connectionError)
            .having((e) => e.response, 'no 401 response', isNull),
      ),
    );

    expect(
      (await rig.store.read())!.refreshToken,
      'refresh-old',
    ); // still signed in
    expect(rig.sessionExpiredCalls, 0);
  });

  test('a server error during refresh keeps the session', () async {
    final adapter = _ScriptedAdapter((options) async {
      return options.path == '/auth/refresh'
          ? _error(500, 'INTERNAL_ERROR')
          : _error(401, 'AUTH_EXPIRED');
    });
    final rig = _Rig(adapter);

    await expectLater(
      rig.dio.get<void>('/me'),
      throwsA(
        isA<DioException>().having(
          (e) => e.response?.statusCode,
          'status',
          500,
        ),
      ),
    );

    expect(await rig.store.read(), isNotNull);
    expect(rig.sessionExpiredCalls, 0);
  });

  test('it never loops: a 401 after the retry is returned as is', () async {
    final adapter = _ScriptedAdapter((options) async {
      return options.path == '/auth/refresh'
          ? _json(200, _tokens('new'))
          : _error(401, 'AUTH_INVALID_TOKEN');
    });
    final rig = _Rig(adapter);

    await expectLater(
      rig.dio.get<void>('/me'),
      throwsA(
        isA<DioException>().having(
          (e) => e.response?.statusCode,
          'status',
          401,
        ),
      ),
    );

    expect(adapter.count('/me'), 2); // the original and ONE retry
    expect(adapter.count('/auth/refresh'), 1);
  });

  test('a 401 without a stored token does not try to refresh', () async {
    final adapter = _ScriptedAdapter(
      (_) async => _error(401, 'AUTH_INVALID_TOKEN'),
    );
    final rig = _Rig(adapter);
    await rig.store.clear();

    await expectLater(rig.dio.get<void>('/me'), throwsA(isA<DioException>()));

    expect(adapter.count('/auth/refresh'), 0);
    expect(rig.sessionExpiredCalls, 0);
  });

  test(
    'other errors (403, 404, 500) are passed on without a refresh',
    () async {
      for (final status in [403, 404, 500]) {
        final adapter = _ScriptedAdapter((_) async => _error(status, 'X'));
        final rig = _Rig(adapter);

        await expectLater(
          rig.dio.get<void>('/me'),
          throwsA(
            isA<DioException>().having(
              (e) => e.response?.statusCode,
              'status',
              status,
            ),
          ),
        );

        expect(adapter.count('/auth/refresh'), 0, reason: 'status $status');
      }
    },
  );
}
