import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../core/networking/dio_provider.dart';
import '../../../core/storage/token_store.dart';
import '../domain/user_profile.dart';

part 'auth_api.g.dart';

/// The backend's auth endpoints (spec 16). Implementations throw on failure; the caller turns
/// the exception into an `ApiError` (core/networking/api_error.dart).
abstract interface class AuthApi {
  Future<AuthTokens> register({
    required String email,
    required String password,
    required bool isAdultConfirmed,
  });
  Future<AuthTokens> login({required String email, required String password});
  Future<void> logout(String refreshToken);
  Future<UserProfile> me();
  Future<void> deleteMe();
}

class DioAuthApi implements AuthApi {
  const DioAuthApi({required Dio publicDio, required Dio authenticatedDio})
    : _public = publicDio,
      _authenticated = authenticatedDio;

  final Dio _public; // no token needed
  final Dio _authenticated; // adds the access token, renews it on 401

  @override
  Future<AuthTokens> register({
    required String email,
    required String password,
    required bool isAdultConfirmed,
  }) async {
    final response = await _public.post<Map<String, dynamic>>(
      '/auth/register',
      data: {
        'email': email,
        'password': password,
        'is_adult_confirmed': isAdultConfirmed,
      },
    );
    return _tokens(response.data!);
  }

  @override
  Future<AuthTokens> login({
    required String email,
    required String password,
  }) async {
    final response = await _public.post<Map<String, dynamic>>(
      '/auth/login',
      data: {'email': email, 'password': password},
    );
    return _tokens(response.data!);
  }

  @override
  Future<void> logout(String refreshToken) async {
    await _public.post<void>(
      '/auth/logout',
      data: {'refresh_token': refreshToken},
    );
  }

  @override
  Future<UserProfile> me() async {
    final response = await _authenticated.get<Map<String, dynamic>>('/me');
    return UserProfile.fromJson(response.data!);
  }

  @override
  Future<void> deleteMe() async {
    await _authenticated.delete<void>('/me');
  }

  AuthTokens _tokens(Map<String, dynamic> json) => AuthTokens(
    accessToken: json['access_token'] as String,
    refreshToken: json['refresh_token'] as String,
  );
}

@Riverpod(keepAlive: true)
AuthApi authApi(Ref ref) {
  return DioAuthApi(
    publicDio: ref.watch(publicDioProvider),
    authenticatedDio: ref.watch(dioProvider),
  );
}
