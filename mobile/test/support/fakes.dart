import 'dart:async';

import 'package:camera/camera.dart' show CameraDescription;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:receiptbox/app.dart';
import 'package:receiptbox/core/networking/api_error.dart';
import 'package:receiptbox/features/analytics/data/analytics_api.dart';
import 'package:receiptbox/features/analytics/data/analytics_providers.dart';
import 'package:receiptbox/core/storage/settings_store.dart';
import 'package:receiptbox/core/storage/token_store.dart';
import 'package:receiptbox/features/auth/data/auth_api.dart';
import 'package:receiptbox/features/auth/domain/user_profile.dart';
import 'package:receiptbox/features/capture/data/capture_providers.dart';
import 'package:receiptbox/features/capture/data/extraction_api.dart';
import 'package:receiptbox/features/capture/domain/bank_models.dart';
import 'package:receiptbox/features/capture/domain/capture_payload.dart';
import 'package:receiptbox/features/capture/domain/extraction_result.dart';
import 'package:receiptbox/features/health/data/health_repository.dart';
import 'package:receiptbox/features/health/domain/health_status.dart';
import 'package:receiptbox/features/transactions/data/transactions_api.dart';

import 'analytics_fakes.dart';
import 'purchase_fakes.dart';

import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/core/theme/app_theme.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'capture_fakes.dart';

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

  /// The server's copy of the AI consent, and what the app asked it to change.
  bool serverAiConsent = false;
  int setAiConsentCalls = 0;
  ApiError? setAiConsentError;

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
      aiConsent: serverAiConsent,
    );
  }

  @override
  Future<UserProfile> setAiConsent(bool value) async {
    setAiConsentCalls++;
    if (setAiConsentError != null) throw setAiConsentError!;
    serverAiConsent = value;
    return me();
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

  // Capture (P04): no camera, no ML Kit, no platform channels in widget tests.
  final FakeCapturePipeline pipeline = FakeCapturePipeline();
  final FakeGalleryPicker gallery = FakeGalleryPicker();
  final FakeSharedMediaSource sharedMedia = FakeSharedMediaSource();
  final FakeExtractionApi extraction = FakeExtractionApi();

  // Purchases (P07).
  final FakeTransactionsApi transactions = FakeTransactionsApi();

  // Home, analytics and budgets (P11), with a fixed "now": 20 November 2026.
  final FakeAnalyticsApi analytics = FakeAnalyticsApi();
  DateTime now = DateTime(2026, 11, 20, 12);
  final FakeDocumentsApi documents = FakeDocumentsApi();

  /// What the camera plugin reports. Default: this phone has no camera.
  Future<List<CameraDescription>> Function() cameras = () async => [];

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
    capturePipelineProvider.overrideWithValue(pipeline),
    galleryPickerProvider.overrideWithValue(gallery),
    sharedMediaSourceProvider.overrideWithValue(sharedMedia),
    extractionApiProvider.overrideWithValue(extraction),
    transactionsApiProvider.overrideWithValue(transactions),
    analyticsApiProvider.overrideWithValue(analytics),
    analyticsClockProvider.overrideWithValue(() => now),
    documentsApiProvider.overrideWithValue(documents),
    captureTempDirProvider.overrideWithValue(NoopTempDir()),
    camerasLoaderProvider.overrideWithValue(() => cameras()),
    healthStatusProvider.overrideWith(
      (ref) async => const HealthStatus(status: 'ok', db: 'ok'),
    ),
  ];

  /// A fresh app (as after killing and restarting it) sharing the same "device" storage.
  Widget app({List<Override> extraOverrides = const []}) => ProviderScope(
    overrides: [...overrides, ...extraOverrides],
    child: const ReceiptBoxApp(),
  );

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

/// The backend's extraction endpoints replaced: tests decide the answer.
class FakeExtractionApi implements ExtractionApi {
  final calls = <({CapturePayload payload, bool aiConsent})>[];
  Object? error;
  Completer<void>? gate;
  ExtractionResult result = const ExtractionResult(
    observationId: 'obs-1',
    merchant: 'MIGROS TICARET A.S.',
    date: '2026-11-14',
    total: '270.30',
    itemCount: 4,
    confidence: {
      'merchant': 'HIGH',
      'date': 'HIGH',
      'total': 'HIGH',
      'items': 'LOW',
    },
    merchantMatch: 'GLOBAL_ALIAS',
    merchantName: 'Migros',
    categoryKey: 'GROCERY',
    categorySource: 'MERCHANT_DEFAULT',
    aiUsed: true,
    usedQr: false,
  );

  // Bank screenshots (P08).
  final bankCalls = <({CapturePayload payload, String? bankHint})>[];
  Object? bankError;
  Completer<void>? bankGate;

  /// What the server answers for a bank screenshot; tests replace it.
  BankImport bankResult = const BankImport(
    bankKey: BankKey.garanti,
    rows: [],
    skipped: [],
  );

  @override
  Future<BankImport> extractBank(
    CapturePayload payload, {
    required String? bankHint,
    required bool aiConsent,
  }) async {
    bankCalls.add((payload: payload, bankHint: bankHint));
    if (!aiConsent) throw const AiConsentOffException();
    if (bankGate != null) await bankGate!.future;
    if (bankError != null) throw bankError!;
    return bankResult;
  }

  @override
  Future<ExtractionResult> extract(
    CapturePayload payload, {
    required bool aiConsent,
  }) async {
    calls.add((payload: payload, aiConsent: aiConsent));
    if (gate != null) await gate!.future;
    if (error != null) throw error!;
    return result;
  }
}
