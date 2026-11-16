import 'package:dio/dio.dart';

import '../storage/token_store.dart';

/// Attaches the access token to requests and silently renews it when it expires.
///
/// Rules (they follow the backend's refresh-token rotation, see docs/PROGRESS.md P02):
/// - On 401 the request is retried **once** with a fresh token. It never loops.
/// - A refresh token can be used only once, so there is **never more than one refresh in
///   flight**: requests that fail at the same time share the same refresh.
/// - A request that was sent with an older access token than the one now stored just retries
///   with the new one; it does not refresh again (that would replay a used refresh token and
///   make the backend revoke the whole session).
/// - If the refresh itself is rejected (401), the session is over: tokens are deleted and
///   [onSessionExpired] runs (the app goes back to the login screen).
/// - If the refresh fails for another reason (no connection, server error) the tokens are
///   kept and the original error is passed on, so a bad network never logs the user out.
class AuthInterceptor extends Interceptor {
  AuthInterceptor({
    required this.tokenStore,
    required this.refreshDio,
    required this.onSessionExpired,
  });

  static const _retriedKey = 'authRetried';

  final TokenStore tokenStore;

  /// A Dio WITHOUT this interceptor, so that refreshing cannot recurse.
  final Dio refreshDio;
  final void Function() onSessionExpired;

  late Dio
  _dio; // the Dio this interceptor is attached to, used to retry requests
  Future<_RefreshResult>? _refreshInFlight;

  /// Call once, right after adding the interceptor to [dio].
  void attach(Dio dio) => _dio = dio;

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final tokens = await tokenStore.read();
    if (tokens != null) {
      options.headers['Authorization'] = 'Bearer ${tokens.accessToken}';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final options = err.requestOptions;
    final sentAuthorization = options.headers['Authorization'] as String?;
    final isExpiredSession =
        err.response?.statusCode == 401 && sentAuthorization != null;
    if (!isExpiredSession || options.extra[_retriedKey] == true) {
      return handler.next(err);
    }

    final result = await _refresh(sentAuthorization);
    switch (result.outcome) {
      case _Outcome.refreshed:
        options.extra[_retriedKey] = true;
        try {
          handler.resolve(await _dio.fetch<dynamic>(options));
        } on DioException catch (retryError) {
          handler.next(retryError);
        }
      case _Outcome.sessionEnded:
        handler.next(
          err,
        ); // the caller sees the 401: the session really is over
      case _Outcome.unavailable:
        // The refresh could not be done (no connection, server error). Report THAT problem,
        // not the 401: a caller must not mistake a bad network for "signed out".
        final cause = result.error!;
        handler.next(
          DioException(
            requestOptions: options,
            type: cause.type,
            response: cause.response,
            error: cause.error,
          ),
        );
    }
  }

  Future<_RefreshResult> _refresh(String sentAuthorization) {
    final inFlight = _refreshInFlight;
    if (inFlight != null) return inFlight;
    final future = _doRefresh(sentAuthorization)
        .whenComplete(() => _refreshInFlight = null);
    _refreshInFlight = future;
    return future;
  }

  Future<_RefreshResult> _doRefresh(String sentAuthorization) async {
    final tokens = await tokenStore.read();
    if (tokens == null) {
      // Already signed out.
      return const _RefreshResult(_Outcome.sessionEnded);
    }
    if ('Bearer ${tokens.accessToken}' != sentAuthorization) {
      // Another request renewed the token after this one was sent: just retry.
      return const _RefreshResult(_Outcome.refreshed);
    }

    try {
      final response = await refreshDio.post<Map<String, dynamic>>(
        '/auth/refresh',
        data: {'refresh_token': tokens.refreshToken},
      );
      final data = response.data!;
      await tokenStore.save(
        AuthTokens(
          accessToken: data['access_token'] as String,
          refreshToken: data['refresh_token'] as String,
        ),
      );
      return const _RefreshResult(_Outcome.refreshed);
    } on DioException catch (error) {
      if (error.response?.statusCode == 401) {
        await tokenStore.clear();
        onSessionExpired();
        return const _RefreshResult(_Outcome.sessionEnded);
      }
      return _RefreshResult(_Outcome.unavailable, error);
    }
  }
}

enum _Outcome { refreshed, sessionEnded, unavailable }

class _RefreshResult {
  const _RefreshResult(this.outcome, [this.error]);

  final _Outcome outcome;

  /// Set when [outcome] is [_Outcome.unavailable].
  final DioException? error;
}
