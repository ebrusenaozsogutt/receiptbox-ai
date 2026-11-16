import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/networking/session_events.dart';
import '../../../core/storage/settings_store.dart';
import '../../../core/storage/token_store.dart';
import '../data/auth_api.dart';
import '../domain/auth_state.dart';

part 'auth_controller.g.dart';

/// Who is signed in. Screens call register/login/logout/deleteAccount; the router reacts to
/// [AuthState] changes. Methods that can fail throw an `ApiError` with a Turkish message.
@Riverpod(keepAlive: true)
class Auth extends _$Auth {
  @override
  AuthState build() {
    // The network layer reports that the backend ended the session (refresh token rejected).
    ref.listen(sessionExpiredSignalProvider, (_, _) {
      state = const AuthState.unauthenticated(sessionExpired: true);
    });
    Future.microtask(restore);
    return const AuthState.checking();
  }

  AuthApi get _api => ref.read(authApiProvider);
  TokenStore get _tokens => ref.read(tokenStoreProvider);

  /// Start-up check: are there stored tokens, and does the backend still accept them?
  /// (The Dio interceptor renews an expired access token silently on the way.)
  Future<void> restore() async {
    state = const AuthState.checking();
    if (await _tokens.read() == null) {
      state = const AuthState.unauthenticated();
      return;
    }
    try {
      final user = await _api.me();
      await ref.read(hasAccountProvider.notifier).set(true);
      state = AuthState.authenticated(user);
    } on Object catch (error) {
      final apiError = apiErrorFrom(error);
      if (apiError.isUnauthorized) {
        await _tokens.clear();
        state = const AuthState.unauthenticated(sessionExpired: true);
      } else {
        // No connection or a server problem: keep the tokens, let the user retry.
        state = AuthState.unreachable(apiError.message);
      }
    }
  }

  Future<void> register({
    required String email,
    required String password,
    required bool isAdultConfirmed,
  }) async {
    try {
      final tokens = await _api.register(
        email: email,
        password: password,
        isAdultConfirmed: isAdultConfirmed,
      );
      await _startSession(tokens);
    } on Object catch (error) {
      throw apiErrorFrom(error);
    }
  }

  Future<void> login({required String email, required String password}) async {
    try {
      final tokens = await _api.login(email: email, password: password);
      await _startSession(tokens);
    } on Object catch (error) {
      throw apiErrorFrom(error);
    }
  }

  Future<void> _startSession(AuthTokens tokens) async {
    await _tokens.save(tokens);
    try {
      final user = await _api.me();
      await ref.read(hasAccountProvider.notifier).set(true);
      state = AuthState.authenticated(user);
    } on Object {
      await _tokens.clear(); // do not keep a half-started session
      rethrow;
    }
  }

  /// Signs out. Revoking the refresh token on the server is best effort: the local sign-out
  /// happens even without a connection.
  Future<void> logout() async {
    final tokens = await _tokens.read();
    if (tokens != null) {
      try {
        await _api.logout(tokens.refreshToken);
      } on Object {
        // ignored on purpose
      }
    }
    await _tokens.clear();
    state = const AuthState.unauthenticated();
  }

  /// Deletes the account on the server, then forgets everything on this device. Afterwards
  /// the router shows Register (this device no longer has an account).
  Future<void> deleteAccount() async {
    try {
      await _api.deleteMe();
    } on Object catch (error) {
      throw apiErrorFrom(error);
    }
    await _tokens.clear();
    await ref.read(hasAccountProvider.notifier).set(false);
    state = const AuthState.unauthenticated();
  }
}
