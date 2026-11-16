// End-to-end check of the P03 acceptance criteria on a real device/emulator, against the real
// backend (docker compose up -d). Not part of CI (CI has no emulator). Run with:
//
//   flutter test integration_test/app_e2e_test.dart -d emulator-5554 \
//       --dart-define=API_BASE_URL=http://10.0.2.2:8000
//
// It creates a throw-away account (e2e-...@example.test) and deletes it again at the end.

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/app.dart';
import 'package:receiptbox/core/config/app_config.dart';
import 'package:receiptbox/core/storage/settings_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _password = 'Parola123';

/// Seconds to stay on each screen, so that screenshots can be taken from outside (adb).
const _pauseSeconds = int.fromEnvironment('SCREENSHOT_PAUSE_SECONDS');

final _backend = Dio(
  BaseOptions(
    baseUrl: '${AppConfig.apiBaseUrl}${AppConfig.apiPrefix}',
    validateStatus: (_) => true, // we look at the status codes ourselves
  ),
);
const _storage = FlutterSecureStorage();

Future<void> _startApp(WidgetTester tester) async {
  // A new ProviderScope is a freshly started app; tokens and preferences stay on the device.
  final prefs = await SharedPreferences.getInstance();
  await tester.pumpWidget(const SizedBox());
  await tester.pumpWidget(
    ProviderScope(
      overrides: [sharedPreferencesProvider.overrideWithValue(prefs)],
      child: const ReceiptBoxApp(),
    ),
  );
}

/// Waits (real time: the network is real) until [finder] shows up.
Future<void> _waitFor(
  WidgetTester tester,
  Finder finder, {
  Duration timeout = const Duration(seconds: 25),
}) async {
  final end = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(end)) {
    await tester.pump(const Duration(milliseconds: 200));
    if (finder.evaluate().isNotEmpty) {
      await tester.pump(const Duration(milliseconds: 300));
      return;
    }
  }
  throw TestFailure('Not found within ${timeout.inSeconds} s: $finder');
}

Future<void> _look(WidgetTester tester, String screen) async {
  debugPrint('E2E screen: $screen');
  if (_pauseSeconds > 0) {
    final end = DateTime.now().add(Duration(seconds: _pauseSeconds));
    while (DateTime.now().isBefore(end)) {
      await tester.pump(const Duration(milliseconds: 250));
    }
  }
}

Future<void> _tap(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await tester.pump(const Duration(milliseconds: 300));
}

Future<void> _login(WidgetTester tester, String email) async {
  await tester.enterText(find.byKey(const Key('login_email')), email);
  await tester.enterText(find.byKey(const Key('login_password')), _password);
  await _tap(tester, find.widgetWithText(FilledButton, 'Giriş yap'));
}

Future<void> _openSettings(WidgetTester tester) async {
  await _tap(tester, find.byTooltip('Ayarlar'));
  await _waitFor(tester, find.text('GİZLİLİK'));
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    'P03 acceptance criteria on the emulator',
    timeout: const Timeout(Duration(minutes: 6)),
    (tester) async {
      final email = 'e2e-${DateTime.now().millisecondsSinceEpoch}@example.test';
      var accountExists = false;

      try {
        // ---- A fresh install -------------------------------------------------------------
        await _storage.deleteAll();
        await (await SharedPreferences.getInstance()).clear();

        // [Criterion 1] Fresh install: consent -> register -> Home.
        await _startApp(tester);
        await _waitFor(tester, find.text('Verilerin senin kontrolünde'));
        await _look(tester, '1 consent');
        await _tap(tester, find.text('Kabul ediyorum'));

        await _waitFor(tester, find.text('Hesap oluştur'));
        await _look(tester, '2 register (empty)');
        await tester.enterText(find.byKey(const Key('register_email')), email);
        await tester.enterText(
          find.byKey(const Key('register_password')),
          _password,
        );
        // The 18+ checkbox is required: without it nothing happens.
        await _tap(tester, find.widgetWithText(FilledButton, 'Kayıt ol'));
        await _waitFor(
          tester,
          find.text(
            'Devam etmek için 18 yaşından büyük olduğunu onaylamalısın.',
          ),
        );
        await _look(tester, '3 register (18+ error)');
        await _tap(tester, find.byType(Checkbox));
        await _tap(tester, find.widgetWithText(FilledButton, 'Kayıt ol'));

        await _waitFor(tester, find.text('Henüz harcama yok'));
        accountExists = true;
        await _look(tester, '4 home (just registered)');
        expect(find.text('Hesap oluştur'), findsNothing);
        expect(await _storage.read(key: 'access_token'), isNotNull);
        expect(await _storage.read(key: 'refresh_token'), isNotNull);
        debugPrint('E2E ok: consent -> register -> Home');

        // ---- Tabs and the (+) sheet --------------------------------------------------------
        for (final entry in {
          'Harcamalar': 'Harcamaların burada listelenecek',
          'Ürünler': 'Ürünlerin burada olacak',
          'Asistan': 'Asistan yakında burada',
        }.entries) {
          await _tap(tester, find.text(entry.key).last);
          await _waitFor(tester, find.text(entry.value));
          await _look(tester, 'tab ${entry.key}');
        }
        await _tap(tester, find.text('Ana Sayfa').last);
        await _waitFor(tester, find.text('Henüz harcama yok'));

        await _tap(tester, find.byKey(const Key('nav_add_button')));
        await _waitFor(tester, find.text('Ne eklemek istersin?'));
        await _look(tester, '5 add sheet');
        for (final title in [
          'Fiş Tara',
          'Galeriden Ekle',
          'Banka Ekran Görüntüsü',
          'Manuel Harcama',
          'Ürün Ekle',
        ]) {
          expect(find.text(title), findsOneWidget, reason: title);
        }
        await _tap(tester, find.text('Banka Ekran Görüntüsü'));
        await _waitFor(tester, find.text('Bu özellik yakında'));
        await _look(tester, '6 placeholder screen');
        await _tap(tester, find.byType(BackButton));
        await _waitFor(tester, find.text('Henüz harcama yok'));
        debugPrint('E2E ok: 4 tabs and 5 (+) actions navigate');

        // ---- [Criterion 1] Restart keeps the session ------------------------------------
        await _startApp(tester);
        await _waitFor(tester, find.text('Henüz harcama yok'));
        expect(find.text('Giriş yap'), findsNothing);
        debugPrint('E2E ok: restart keeps the session');

        // ---- [Criterion 2a] An expired access token is renewed silently -----------------
        final refreshBefore = await _storage.read(key: 'refresh_token');
        await _storage.write(key: 'access_token', value: 'expired-or-garbage');
        await _startApp(tester); // the new app reads the bad token and asks /me
        await _waitFor(tester, find.text('Henüz harcama yok'));
        expect(
          find.text('Giriş yap'),
          findsNothing,
        ); // no login screen in between
        final accessAfter = await _storage.read(key: 'access_token');
        final refreshAfter = await _storage.read(key: 'refresh_token');
        expect(accessAfter, isNot('expired-or-garbage')); // renewed
        expect(
          refreshAfter,
          isNot(refreshBefore),
        ); // the refresh token was rotated
        debugPrint('E2E ok: expired access token refreshed silently');

        // ---- [Criterion 2b] A revoked refresh token sends the user to Login ---------------
        final logout = await _backend.post<void>(
          '/auth/logout',
          data: {'refresh_token': refreshAfter},
        );
        expect(
          logout.statusCode,
          204,
        ); // the backend now revokes that refresh token
        await _storage.write(key: 'access_token', value: 'expired-or-garbage');
        await _startApp(tester);
        await _waitFor(tester, find.text('Giriş yap'));
        await _look(tester, '7 login (session ended)');
        expect(
          find.text('Oturum süren doldu. Lütfen tekrar giriş yap.'),
          findsOneWidget,
        );
        expect(await _storage.read(key: 'refresh_token'), isNull);
        debugPrint('E2E ok: revoked refresh token -> Login');

        // ---- Login with a wrong, then the right password ----------------------------------
        await tester.enterText(find.byKey(const Key('login_email')), email);
        await tester.enterText(
          find.byKey(const Key('login_password')),
          'Yanlis-parola9',
        );
        await _tap(tester, find.widgetWithText(FilledButton, 'Giriş yap'));
        await _waitFor(tester, find.text('E-posta veya parola hatalı.'));
        await _look(tester, '8 login (wrong password)');
        await _login(tester, email);
        await _waitFor(tester, find.text('Henüz harcama yok'));
        debugPrint('E2E ok: login');

        // ---- Settings: privacy toggle and logout ------------------------------------------
        await _openSettings(tester);
        await _look(tester, '9 settings');
        expect(find.text(email), findsOneWidget);
        expect(find.text('Sunucu: bağlı'), findsOneWidget);
        final toggle = find.byType(Switch);
        expect(tester.widget<Switch>(toggle).value, isTrue); // default ON
        await _tap(tester, toggle);
        expect(tester.widget<Switch>(toggle).value, isFalse);
        await _tap(tester, toggle);

        await _tap(tester, find.text('Çıkış yap'));
        await _waitFor(tester, find.text('Giriş yap'));
        await _look(tester, '10 login (after logout)');
        expect(find.text('Hesap oluştur'), findsNothing); // Login, not Register
        expect(await _storage.read(key: 'refresh_token'), isNull);
        debugPrint('E2E ok: logout -> Login');

        await _login(tester, email);
        await _waitFor(tester, find.text('Henüz harcama yok'));

        // ---- [Criterion 3] Delete account -> Register ------------------------------------
        await _openSettings(tester);
        await _tap(tester, find.text('Hesabı sil'));
        await _waitFor(tester, find.text('Hesabını sil?'));
        await _look(tester, '11 delete confirmation');
        await _tap(tester, find.widgetWithText(FilledButton, 'Hesabı sil'));
        await _waitFor(tester, find.text('Hesap oluştur'));
        accountExists = false;
        await _look(tester, '12 register (after deleting the account)');
        expect(await _storage.read(key: 'access_token'), isNull);

        final afterDelete = await _backend.post<Map<String, dynamic>>(
          '/auth/login',
          data: {'email': email, 'password': _password},
        );
        expect(afterDelete.statusCode, 401); // the account is really gone
        debugPrint(
          'E2E ok: delete account -> Register, account gone on the server',
        );
      } finally {
        if (accountExists) {
          // A step failed in the middle: remove the throw-away account.
          final login = await _backend.post<Map<String, dynamic>>(
            '/auth/login',
            data: {'email': email, 'password': _password},
          );
          if (login.statusCode == 200) {
            await _backend.delete<void>(
              '/me',
              options: Options(
                headers: {
                  'Authorization': 'Bearer ${login.data!['access_token']}',
                },
              ),
            );
          }
        }
      }
    },
  );
}
