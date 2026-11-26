import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/core/networking/session_events.dart';

import 'support/fakes.dart';
import 'support/settings_helpers.dart';

Future<void> _openApp(WidgetTester tester, TestApp app) async {
  // A new ProviderScope = a freshly started app. Device storage (tokens, preferences) stays.
  await tester.pumpWidget(const SizedBox());
  await tester.pumpWidget(app.app());
  await tester.pumpAndSettle();
}

Future<void> _register(WidgetTester tester) async {
  await tester.enterText(
    find.byKey(const Key('register_email')),
    'ebru@example.com',
  );
  await tester.enterText(
    find.byKey(const Key('register_password')),
    'Parola123',
  );
  final box = find.byType(Checkbox);
  await tester.ensureVisible(box);
  await tester.tap(box);
  await tester.pump();
  final button = find.widgetWithText(FilledButton, 'Kayıt ol');
  await tester.ensureVisible(button);
  await tester.tap(button);
  await tester.pumpAndSettle();
}

Future<void> _openSettings(WidgetTester tester) async {
  await tester.tap(find.byTooltip('Ayarlar'));
  await tester.pumpAndSettle();
}

void main() {
  group('fresh install', () {
    testWidgets('consent -> register -> Home', (tester) async {
      final app = await TestApp.create();
      await _openApp(tester, app);

      // 1. First run: consent comes first.
      expect(find.text('Verilerin senin kontrolünde'), findsOneWidget);
      await tester.tap(find.text('Kabul ediyorum'));
      await tester.pumpAndSettle();

      // 2. A device with no account starts at Register.
      expect(find.text('Hesap oluştur'), findsOneWidget);
      await _register(tester);

      // 3. Signed in: Home with the bottom navigation.
      expect(find.byKey(const Key('home_list')), findsOneWidget);
      expect(find.text('Ana Sayfa'), findsWidgets);
      expect(find.text('Hesap oluştur'), findsNothing);
      expect(app.api.registerCalls, 1);
      expect(app.tokens.tokens, isNotNull);
      expect(app.preferences.getBool('has_account'), isTrue);
    });

    testWidgets('declining the consent still lets the user register', (
      tester,
    ) async {
      final app = await TestApp.create();
      await _openApp(tester, app);

      await tester.tap(find.text('Şimdilik kabul etmiyorum'));
      await tester.pumpAndSettle();

      expect(find.text('Hesap oluştur'), findsOneWidget);
      expect(app.preferences.getBool('ai_consent'), isFalse);
    });

    testWidgets('"Giriş yap" and "Kayıt ol" links switch between the forms', (
      tester,
    ) async {
      final app = await TestApp.create(preferences: {'consent_seen': true});
      await _openApp(tester, app);
      expect(find.text('Hesap oluştur'), findsOneWidget);

      await tester.tap(find.text('Zaten hesabın var mı? Giriş yap'));
      await tester.pumpAndSettle();
      expect(find.text('Giriş yap'), findsWidgets);
      expect(find.text('Hesap oluştur'), findsNothing);

      await tester.tap(find.text('Hesabın yok mu? Kayıt ol'));
      await tester.pumpAndSettle();
      expect(find.text('Hesap oluştur'), findsOneWidget);
    });
  });

  group('restart', () {
    testWidgets('keeps the session: straight to Home, no login', (
      tester,
    ) async {
      final app = await TestApp.create();
      await _openApp(tester, app);
      await tester.tap(find.text('Kabul ediyorum'));
      await tester.pumpAndSettle();
      await _register(tester);
      expect(find.byKey(const Key('home_list')), findsOneWidget);

      await _openApp(tester, app); // kill and start the app again

      expect(find.byKey(const Key('home_list')), findsOneWidget);
      expect(find.text('Giriş yap'), findsNothing);
      expect(find.text('Verilerin senin kontrolünde'), findsNothing);
    });

    testWidgets(
      'after a revoked session it opens on Login with an explanation',
      (tester) async {
        final app = await TestApp.signedIn();
        app.api.meError = apiError('AUTH_INVALID_TOKEN', status: 401);

        await _openApp(tester, app);

        expect(find.text('Giriş yap'), findsWidgets);
        expect(
          find.text('Oturum süren doldu. Lütfen tekrar giriş yap.'),
          findsOneWidget,
        );
        expect(app.tokens.tokens, isNull); // the dead tokens were removed
      },
    );

    testWidgets('without a connection it stays signed in and offers a retry', (
      tester,
    ) async {
      final app = await TestApp.signedIn();
      app.api.meError = apiError('NETWORK_UNREACHABLE');
      await _openApp(tester, app);

      expect(
        find.text('Sunucuya ulaşılamıyor. İnternet bağlantını kontrol et.'),
        findsOneWidget,
      );
      expect(
        app.tokens.tokens,
        isNotNull,
      ); // a bad network does not sign anyone out
      expect(find.text('Giriş yap'), findsNothing);

      app.api.meError = null; // the network is back
      await tester.tap(find.text('Tekrar dene'));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('home_list')), findsOneWidget);
    });
  });

  group('while using the app', () {
    testWidgets('a refresh the backend rejects sends the user back to Login', (
      tester,
    ) async {
      final app = await TestApp.signedIn();
      await _openApp(tester, app);
      expect(find.byKey(const Key('home_list')), findsOneWidget);

      // The network layer announces this when the refresh token is rejected.
      ProviderScope.containerOf(tester.element(find.byType(MaterialApp)))
          .read(sessionExpiredSignalProvider.notifier)
          .signal();
      await tester.pumpAndSettle();

      expect(find.text('Giriş yap'), findsWidgets);
      expect(
        find.text('Oturum süren doldu. Lütfen tekrar giriş yap.'),
        findsOneWidget,
      );
    });
  });

  group('sign out', () {
    testWidgets('Settings -> Çıkış yap -> Login, and signing in works again', (
      tester,
    ) async {
      final app = await TestApp.signedIn();
      await _openApp(tester, app);
      await _openSettings(tester);

      await scrollSettingsTo(tester, find.text('Çıkış yap'));
      await tester.tap(find.text('Çıkış yap'));
      await tester.pumpAndSettle();

      expect(find.text('Giriş yap'), findsWidgets);
      expect(find.text('Hesap oluştur'), findsNothing);
      expect(app.api.logoutCalls, 1);
      expect(app.tokens.tokens, isNull);
      expect(
        find.text('Oturum süren doldu. Lütfen tekrar giriş yap.'),
        findsNothing,
      );

      await tester.enterText(
        find.byKey(const Key('login_email')),
        'ebru@example.com',
      );
      await tester.enterText(
        find.byKey(const Key('login_password')),
        'Parola123',
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Giriş yap'));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('home_list')), findsOneWidget);
    });

    testWidgets('after logout a restart opens on Login, not on Home', (
      tester,
    ) async {
      final app = await TestApp.signedIn();
      await _openApp(tester, app);
      await _openSettings(tester);
      await scrollSettingsTo(tester, find.text('Çıkış yap'));
      await tester.tap(find.text('Çıkış yap'));
      await tester.pumpAndSettle();

      await _openApp(tester, app);

      expect(find.text('Giriş yap'), findsWidgets);
      expect(find.byKey(const Key('home_list')), findsNothing);
    });
  });

  group('delete account', () {
    testWidgets('confirm -> account deleted -> Register', (tester) async {
      final app = await TestApp.signedIn();
      await _openApp(tester, app);
      await _openSettings(tester);

      await scrollSettingsTo(tester, find.text('Hesabı sil'));
      await tester.tap(find.text('Hesabı sil'));
      await tester.pumpAndSettle();
      expect(
        find.text('Hesabını sil?'),
        findsOneWidget,
      ); // the confirmation dialog
      expect(find.textContaining('geri alınamaz'), findsOneWidget);
      expect(
        app.api.deleteCalls,
        0,
      ); // nothing happens before the user confirms

      await tester.tap(find.widgetWithText(FilledButton, 'Hesabı sil'));
      await tester.pumpAndSettle();

      expect(app.api.deleteCalls, 1);
      expect(find.text('Hesap oluştur'), findsOneWidget); // back at Register
      expect(app.tokens.tokens, isNull);
      expect(app.preferences.getBool('has_account'), isFalse);
    });

    testWidgets('"İptal" keeps everything', (tester) async {
      final app = await TestApp.signedIn();
      await _openApp(tester, app);
      await _openSettings(tester);

      await scrollSettingsTo(tester, find.text('Hesabı sil'));
      await tester.tap(find.text('Hesabı sil'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('İptal'));
      await tester.pumpAndSettle();

      expect(app.api.deleteCalls, 0);
      expect(
        find.text('Ayarlar'),
        findsWidgets,
      ); // still on the Settings screen
      expect(app.tokens.tokens, isNotNull);
    });

    testWidgets('a server error is shown and the user stays signed in', (
      tester,
    ) async {
      final app = await TestApp.signedIn();
      app.api.deleteError = apiError('INTERNAL_ERROR', status: 500);
      await _openApp(tester, app);
      await _openSettings(tester);

      await scrollSettingsTo(tester, find.text('Hesabı sil'));
      await tester.tap(find.text('Hesabı sil'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Hesabı sil'));
      await tester.pumpAndSettle();

      expect(
        find.text('Sunucuda bir sorun oluştu. Biraz sonra tekrar dene.'),
        findsOneWidget,
      );
      expect(app.tokens.tokens, isNotNull);
      expect(find.text('Hesap oluştur'), findsNothing);
    });

    testWidgets('after deletion a restart opens on Register', (tester) async {
      final app = await TestApp.signedIn();
      await _openApp(tester, app);
      await _openSettings(tester);
      await scrollSettingsTo(tester, find.text('Hesabı sil'));
      await tester.tap(find.text('Hesabı sil'));
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Hesabı sil'));
      await tester.pumpAndSettle();

      await _openApp(tester, app);

      expect(find.text('Hesap oluştur'), findsOneWidget);
    });
  });
}
