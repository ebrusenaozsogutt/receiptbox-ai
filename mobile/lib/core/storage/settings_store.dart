import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:shared_preferences/shared_preferences.dart';

part 'settings_store.g.dart';

/// Small local settings (shared_preferences). No secrets here: tokens are in the secure store.
class SettingsStore {
  const SettingsStore(this._prefs);

  final SharedPreferences _prefs;

  static const _consentSeenKey = 'consent_seen';
  static const _aiConsentKey = 'ai_consent';
  static const _keepReceiptImagesKey = 'keep_receipt_images';
  static const _hasAccountKey = 'has_account';

  /// The first-run consent screen has been completed (accepted or declined).
  bool get consentSeen => _prefs.getBool(_consentSeenKey) ?? false;

  /// The user agreed that masked text is processed by an external AI provider (spec 15.3).
  /// Without it only manual entry is possible; the extraction phases check this.
  bool get aiConsent => _prefs.getBool(_aiConsentKey) ?? false;

  /// "Fiş görsellerini sakla": default ON, receipt photos are warranty proof (spec 15.3).
  bool get keepReceiptImages => _prefs.getBool(_keepReceiptImagesKey) ?? true;

  /// This device has had an account (signed in or registered, and not deleted since).
  /// Decides whether a signed-out user lands on Login (true) or Register (false).
  bool get hasAccount => _prefs.getBool(_hasAccountKey) ?? false;

  Future<void> saveConsent({required bool aiConsent}) async {
    await _prefs.setBool(_aiConsentKey, aiConsent);
    await _prefs.setBool(_consentSeenKey, true);
  }

  Future<void> setKeepReceiptImages(bool value) =>
      _prefs.setBool(_keepReceiptImagesKey, value);

  Future<void> setHasAccount(bool value) =>
      _prefs.setBool(_hasAccountKey, value);
}

/// Overridden in main() with the real instance (it is created asynchronously).
@Riverpod(keepAlive: true)
SharedPreferences sharedPreferences(Ref ref) =>
    throw UnimplementedError('sharedPreferencesProvider must be overridden');

@Riverpod(keepAlive: true)
SettingsStore settingsStore(Ref ref) =>
    SettingsStore(ref.watch(sharedPreferencesProvider));

/// Reactive views of the settings, so the router and screens rebuild when they change.
@Riverpod(keepAlive: true)
class ConsentSeen extends _$ConsentSeen {
  @override
  bool build() => ref.read(settingsStoreProvider).consentSeen;

  Future<void> accept({required bool aiConsent}) async {
    await ref.read(settingsStoreProvider).saveConsent(aiConsent: aiConsent);
    state = true;
  }
}

@Riverpod(keepAlive: true)
class KeepReceiptImages extends _$KeepReceiptImages {
  @override
  bool build() => ref.read(settingsStoreProvider).keepReceiptImages;

  Future<void> set(bool value) async {
    await ref.read(settingsStoreProvider).setKeepReceiptImages(value);
    state = value;
  }
}

@Riverpod(keepAlive: true)
class HasAccount extends _$HasAccount {
  @override
  bool build() => ref.read(settingsStoreProvider).hasAccount;

  Future<void> set(bool value) async {
    await ref.read(settingsStoreProvider).setHasAccount(value);
    state = value;
  }
}
