import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../config/app_config.dart';
import '../storage/token_store.dart';
import 'auth_interceptor.dart';
import 'data_changed.dart';
import 'session_events.dart';

part 'dio_provider.g.dart';

// No LogInterceptor on purpose: request/response bodies can contain personal data and
// tokens and must never be printed (see CLAUDE.md privacy rules).
Dio _newDio() {
  return Dio(
    BaseOptions(
      baseUrl: '${AppConfig.apiBaseUrl}${AppConfig.apiPrefix}',
      connectTimeout: const Duration(seconds: 5),
      receiveTimeout: const Duration(seconds: 10),
    ),
  );
}

/// For endpoints that need no token (register, login, refresh, logout, health).
@Riverpod(keepAlive: true)
Dio publicDio(Ref ref) => _newDio();

/// The Dio used by all features: attaches the access token and renews it on 401.
@Riverpod(keepAlive: true)
Dio dio(Ref ref) {
  final dio = _newDio();
  final interceptor = AuthInterceptor(
    tokenStore: ref.watch(tokenStoreProvider),
    refreshDio: ref.watch(publicDioProvider),
    onSessionExpired: () =>
        ref.read(sessionExpiredSignalProvider.notifier).signal(),
  );
  dio.interceptors.add(interceptor);
  interceptor.attach(dio);
  // P13: a successful write may move a reminder deadline.
  dio.interceptors.add(
    DataChangedInterceptor(
      () => ref.read(dataChangedSignalProvider.notifier).signal(),
    ),
  );
  return dio;
}
