import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

import '../../support/fakes.dart';

Future<TestApp> _signedIn(
  WidgetTester tester, {
  bool deviceConsent = false,
  bool serverConsent = false,
  void Function(TestApp app)? beforeStart,
}) async {
  final base = await TestApp.signedIn();
  final app = await TestApp.create(
    api: base.api,
    tokens: base.tokens,
    preferences: {
      'consent_seen': true,
      'has_account': true,
      if (deviceConsent) 'ai_consent': true,
    },
  );
  app.api.serverAiConsent = serverConsent;
  beforeStart?.call(app);
  await tester.pumpWidget(app.app());
  await tester.pumpAndSettle();
  return app;
}

Future<void> _openSettings(WidgetTester tester) async {
  await tester.tap(find.byTooltip('Ayarlar'));
  await tester.pumpAndSettle();
}

final _aiSwitch = find.descendant(
  of: find.byKey(const Key('ai_consent_switch')),
  matching: find.byType(Switch),
);

void main() {
  group('keeping the device and the server equal', () {
    testWidgets(
      'a consent given on the device is sent to the server at start',
      (tester) async {
        final app = await _signedIn(tester, deviceConsent: true);

        expect(app.api.setAiConsentCalls, 1);
        expect(app.api.serverAiConsent, isTrue);
      },
    );

    testWidgets('nothing is sent when both already agree', (tester) async {
      final yes = await _signedIn(
        tester,
        deviceConsent: true,
        serverConsent: true,
      );
      expect(yes.api.setAiConsentCalls, 0);

      final no = await _signedIn(tester);
      expect(no.api.setAiConsentCalls, 0);
    });

    testWidgets('a declined consent on the device switches the server off', (
      tester,
    ) async {
      final app = await _signedIn(tester, serverConsent: true);

      expect(app.api.serverAiConsent, isFalse);
    });

    testWidgets('a server that cannot be reached does not stop the app', (
      tester,
    ) async {
      final app = await _signedIn(
        tester,
        deviceConsent: true,
        beforeStart: (app) =>
            app.api.setAiConsentError = apiError('NETWORK_ERROR'),
      );

      expect(app.api.setAiConsentCalls, 1);
      expect(find.text('Ana Sayfa'), findsWidgets); // still signed in, on Home
    });

    testWidgets(
      'the consent screen choice reaches the server at registration',
      (tester) async {
        final app = await TestApp.create();
        await tester.pumpWidget(app.app());
        await tester.pumpAndSettle();
        await tester.tap(find.text('Kabul ediyorum'));
        await tester.pumpAndSettle();

        await tester.enterText(
          find.byKey(const Key('register_email')),
          'yeni@example.com',
        );
        await tester.enterText(
          find.byKey(const Key('register_password')),
          'Parola123',
        );
        await tester.tap(find.byKey(const Key('adult_confirmation')));
        await tester.tap(find.widgetWithText(FilledButton, 'Kayıt ol'));
        await tester.pumpAndSettle();

        expect(app.api.serverAiConsent, isTrue);
      },
    );
  });

  group('Settings switch "Yapay zekâ ile fiş okuma"', () {
    testWidgets('is off by default and explains what it does', (tester) async {
      await _signedIn(tester);
      await _openSettings(tester);

      expect(find.text('Yapay zekâ ile fiş okuma'), findsOneWidget);
      expect(find.textContaining('yalnızca elle giriş'), findsOneWidget);
      expect(tester.widget<Switch>(_aiSwitch).value, isFalse);
    });

    testWidgets('turning it on is saved on the device and on the server', (
      tester,
    ) async {
      final app = await _signedIn(tester);
      await _openSettings(tester);

      await tester.tap(_aiSwitch);
      await tester.pumpAndSettle();

      expect(tester.widget<Switch>(_aiSwitch).value, isTrue);
      expect(app.preferences.getBool('ai_consent'), isTrue);
      expect(app.api.serverAiConsent, isTrue);
    });

    testWidgets('turning it off again withdraws the consent everywhere', (
      tester,
    ) async {
      final app = await _signedIn(
        tester,
        deviceConsent: true,
        serverConsent: true,
      );
      await _openSettings(tester);

      await tester.tap(_aiSwitch);
      await tester.pumpAndSettle();

      expect(tester.widget<Switch>(_aiSwitch).value, isFalse);
      expect(app.preferences.getBool('ai_consent'), isFalse);
      expect(app.api.serverAiConsent, isFalse);
    });

    testWidgets(
      'when the server is unreachable the device keeps the choice and says so',
      (tester) async {
        final app = await _signedIn(tester);
        app.api.setAiConsentError = apiError('NETWORK_ERROR');
        await _openSettings(tester);

        await tester.tap(_aiSwitch);
        await tester.pumpAndSettle();

        expect(tester.widget<Switch>(_aiSwitch).value, isTrue);
        expect(app.preferences.getBool('ai_consent'), isTrue);
        expect(find.textContaining('sunucuya iletilemedi'), findsOneWidget);
      },
    );

    testWidgets('the receipt-images switch is a separate switch', (
      tester,
    ) async {
      final app = await _signedIn(tester);
      await _openSettings(tester);

      expect(find.byType(Switch), findsNWidgets(2));
      await tester.tap(_aiSwitch);
      await tester.pumpAndSettle();

      expect(app.preferences.getBool('keep_receipt_images'), isNull);
    });
  });
}
