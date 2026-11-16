import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:receiptbox/app.dart';
import 'package:receiptbox/core/networking/api_error.dart';
import 'package:receiptbox/core/storage/settings_store.dart';
import 'package:receiptbox/core/storage/token_store.dart';
import 'package:receiptbox/features/auth/data/auth_api.dart';
import 'package:receiptbox/features/auth/domain/user_profile.dart';
import 'package:receiptbox/features/health/data/health_repository.dart';
import 'package:receiptbox/features/health/domain/health_status.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/core/theme/app_theme.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Tokens kept in memory (the real store is the Android Keystore).
class InMemoryTokenStore implements TokenStore {
  InMemoryTokenStore([this.tokens]);

  AuthTokens? tokens;

  @override
  Future<AuthTokens?> read() async => tokens;

  @override
  Future<void> save(AuthTokens value) async => tokens = value;

  @override
  Future<void> clear() async => tokens = null;
}

ApiError apiError(String code, {int? status}) =>
    ApiError(code: code, message: messageForCode(code), statusCode: status);

/// A stand-in for the backend's auth endpoints.
class FakeAuthApi implements AuthApi {
  final Map<String, String> passwords = {}; // e-mail -> password
  String? signedInEmail;

  int registerCalls = 0;
  int loginCalls = 0;
  int logoutCalls = 0;
  int deleteCalls = 0;
  int meCalls = 0;

  ApiError? registerError;
  ApiError? loginError;
  ApiError? meError;
  ApiError? deleteError;
  bool? lastIsAdultConfirmed;

  /// When set, login() waits for it: lets a test look at the "request in progress" state.
  Completer<void>? loginGate;

  int _counter = 0;

  AuthTokens _newTokens() {
    _counter++;
    return AuthTokens(
      accessToken: 'access-$_counter',
      refreshToken: 'refresh-$_counter',
    );
  }

  @override
  Future<AuthTokens> register({
    required String email,
    required String password,
    required bool isAdultConfirmed,
  }) async {
    registerCalls++;
    lastIsAdultConfirmed = isAdultConfirmed;
    if (registerError != null) throw registerError!;
    if (passwords.containsKey(email)) {
      throw apiError('EMAIL_ALREADY_REGISTERED', status: 409);
    }
    passwords[email] = password;
    signedInEmail = email;
    return _newTokens();
  }

  @override
  Future<AuthTokens> login({
    required String email,
    required String password,
  }) async {
    loginCalls++;
    if (loginGate != null) await loginGate!.future;
    if (loginError != null) throw loginError!;
    if (passwords[email] != password) {
      throw apiError('AUTH_INVALID_CREDENTIALS', status: 401);
    }
    signedInEmail = email;
    return _newTokens();
  }

  @override
  Future<void> logout(String refreshToken) async {
    logoutCalls++;
    signedInEmail = null;
  }

  @override
  Future<UserProfile> me() async {
    meCalls++;
    if (meError != null) throw meError!;
    final email = signedInEmail;
    if (email == null) throw apiError('AUTH_INVALID_TOKEN', status: 401);
    return UserProfile(
      id: 'user-1',
      email: email,
      isAdultConfirmed: true,
      createdAt: DateTime(2026, 11, 16),
    );
  }

  @override
  Future<void> deleteMe() async {
    deleteCalls++;
    if (deleteError != null) throw deleteError!;
    passwords.remove(signedInEmail);
    signedInEmail = null;
  }
}

/// The whole app with fake backend, token store and preferences.
class TestApp {
  TestApp._(this.api, this.tokens, this.preferences);

  final FakeAuthApi api;
  final InMemoryTokenStore tokens;
  final SharedPreferences preferences;

  static Future<TestApp> create({
    FakeAuthApi? api,
    InMemoryTokenStore? tokens,
    Map<String, Object> preferences = const {},
  }) async {
    SharedPreferences.setMockInitialValues(preferences);
    return TestApp._(
      api ?? FakeAuthApi(),
      tokens ?? InMemoryTokenStore(),
      await SharedPreferences.getInstance(),
    );
  }

  List<Override> get overrides => [
    authApiProvider.overrideWithValue(api),
    tokenStoreProvider.overrideWithValue(tokens),
    sharedPreferencesProvider.overrideWithValue(preferences),
    healthStatusProvider.overrideWith(
      (ref) async => const HealthStatus(status: 'ok', db: 'ok'),
    ),
  ];

  /// A fresh app (as after killing and restarting it) sharing the same "device" storage.
  Widget app() =>
      ProviderScope(overrides: overrides, child: const ReceiptBoxApp());

  /// One screen on its own (no router), with the real theme and Turkish localization.
  Widget screen(Widget child) => ProviderScope(
    overrides: overrides,
    child: MaterialApp(
      theme: AppTheme.light(),
      locale: const Locale('tr', 'TR'),
      supportedLocales: const [Locale('tr', 'TR')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      home: child,
    ),
  );

  /// Pretends the user is signed in on this device (tokens stored, consent given).
  static Future<TestApp> signedIn({String email = 'ebru@example.com'}) async {
    final api = FakeAuthApi()
      ..passwords[email] = 'Parola123'
      ..signedInEmail = email;
    return TestApp.create(
      api: api,
      tokens: InMemoryTokenStore(
        const AuthTokens(accessToken: 'access-0', refreshToken: 'refresh-0'),
      ),
      preferences: {'consent_seen': true, 'has_account': true},
    );
  }
}
