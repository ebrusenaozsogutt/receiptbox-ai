import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../config/app_config.dart';

part 'dio_provider.g.dart';

/// The single Dio instance used by all features.
///
/// No LogInterceptor on purpose: request/response bodies can contain personal data
/// and must never be printed (see CLAUDE.md privacy rules).
@Riverpod(keepAlive: true)
Dio dio(Ref ref) {
  return Dio(
    BaseOptions(
      baseUrl: '${AppConfig.apiBaseUrl}${AppConfig.apiPrefix}',
      connectTimeout: const Duration(seconds: 5),
      receiveTimeout: const Duration(seconds: 10),
      // 503 is accepted so the app can tell "server up, database down" from "no connection".
      // Every other non-200 answer is treated as an error.
      validateStatus: (status) => status == 200 || status == 503,
    ),
  );
}
