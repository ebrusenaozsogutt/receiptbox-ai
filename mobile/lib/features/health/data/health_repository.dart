import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../core/networking/dio_provider.dart';
import '../domain/health_status.dart';

part 'health_repository.g.dart';

class HealthRepository {
  const HealthRepository(this._dio);

  final Dio _dio;

  /// Throws [DioException] when the server cannot be reached.
  Future<HealthStatus> fetch() async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/health',
      // 503 is a valid answer here ("server up, database down"), not a failure.
      options: Options(
        validateStatus: (status) => status == 200 || status == 503,
      ),
    );
    return HealthStatus.fromJson(response.data!);
  }
}

@riverpod
HealthRepository healthRepository(Ref ref) {
  return HealthRepository(ref.watch(publicDioProvider));
}

/// Riverpod 3 retries failed providers automatically. Here the user retries with a button,
/// and the screen must show "bağlantı yok" right away instead of an endless spinner.
Duration? _noRetry(int retryCount, Object error) => null;

/// Calls the backend once; invalidate it to retry.
@Riverpod(retry: _noRetry)
Future<HealthStatus> healthStatus(Ref ref) {
  return ref.watch(healthRepositoryProvider).fetch();
}
