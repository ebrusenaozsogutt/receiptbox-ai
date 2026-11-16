import 'dart:async';

import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/core/networking/api_error.dart';
import 'package:receiptbox/core/storage/token_store.dart';
import 'package:receiptbox/features/auth/presentation/login_screen.dart';

import '../../support/fakes.dart';

Future<void> _type(WidgetTester tester, String key, String text) async {
  await tester.enterText(find.byKey(Key(key)), text);
}

Future<void> _submit(WidgetTester tester) async {
  await tester.tap(find.widgetWithText(FilledButton, 'Giriş yap'));
  await tester.pumpAndSettle();
}

bool _isObscured(WidgetTester tester, String key) => tester
    .widget<EditableText>(
      find.descendant(
        of: find.byKey(Key(key)),
        matching: find.byType(EditableText),
      ),
    )
    .obscureText;

void main() {
  testWidgets('empty fields show Turkish messages and nothing is sent', (
    tester,
  ) async {
    final app = await TestApp.create();
    await tester.pumpWidget(app.screen(const LoginScreen()));

    await _submit(tester);

    expect(find.text('E-posta adresini gir.'), findsOneWidget);
    expect(find.text('Parolanı gir.'), findsOneWidget);
    expect(app.api.loginCalls, 0);
  });

  testWidgets('a malformed e-mail is rejected before any request', (
    tester,
  ) async {
    final app = await TestApp.create();
    await tester.pumpWidget(app.screen(const LoginScreen()));

    await _type(tester, 'login_email', 'not-an-email');
    await _type(tester, 'login_password', 'Parola123');
    await _submit(tester);

    expect(find.text('Geçerli bir e-posta adresi gir.'), findsOneWidget);
    expect(app.api.loginCalls, 0);
  });

  testWidgets('valid input logs in (the e-mail is trimmed)', (tester) async {
    final api = FakeAuthApi()..passwords['ebru@example.com'] = 'Parola123';
    final app = await TestApp.create(api: api);
    await tester.pumpWidget(app.screen(const LoginScreen()));

    await _type(tester, 'login_email', '  ebru@example.com ');
    await _type(tester, 'login_password', 'Parola123');
    await _submit(tester);

    expect(api.loginCalls, 1);
    expect(app.tokens.tokens, isNotNull); // the session was stored
  });

  testWidgets('a wrong password shows the server error in Turkish', (
    tester,
  ) async {
    final api = FakeAuthApi()..passwords['ebru@example.com'] = 'Parola123';
    final app = await TestApp.create(api: api);
    await tester.pumpWidget(app.screen(const LoginScreen()));

    await _type(tester, 'login_email', 'ebru@example.com');
    await _type(tester, 'login_password', 'Yanlis-parola1');
    await _submit(tester);

    expect(find.text('E-posta veya parola hatalı.'), findsOneWidget);
    expect(app.tokens.tokens, isNull);
  });

  testWidgets('rate limiting tells the user how long to wait', (tester) async {
    final api = FakeAuthApi()
      ..loginError = ApiError(
        code: 'RATE_LIMITED',
        message: messageForCode('RATE_LIMITED', retryAfterSeconds: 30),
        statusCode: 429,
        retryAfterSeconds: 30,
      );
    final app = await TestApp.create(api: api);
    await tester.pumpWidget(app.screen(const LoginScreen()));

    await _type(tester, 'login_email', 'ebru@example.com');
    await _type(tester, 'login_password', 'Parola123');
    await _submit(tester);

    expect(
      find.text('Çok fazla deneme yaptın. 30 saniye sonra tekrar dene.'),
      findsOneWidget,
    );
  });

  testWidgets('no connection shows a connection message', (tester) async {
    final api = FakeAuthApi()..loginError = apiError('NETWORK_UNREACHABLE');
    final app = await TestApp.create(api: api);
    await tester.pumpWidget(app.screen(const LoginScreen()));

    await _type(tester, 'login_email', 'ebru@example.com');
    await _type(tester, 'login_password', 'Parola123');
    await _submit(tester);

    expect(
      find.text('Sunucuya ulaşılamıyor. İnternet bağlantını kontrol et.'),
      findsOneWidget,
    );
  });

  testWidgets('the eye button shows and hides the password', (tester) async {
    final app = await TestApp.create();
    await tester.pumpWidget(app.screen(const LoginScreen()));
    expect(_isObscured(tester, 'login_password'), isTrue);

    await tester.tap(find.byTooltip('Parolayı göster'));
    await tester.pump();
    expect(_isObscured(tester, 'login_password'), isFalse);

    await tester.tap(find.byTooltip('Parolayı gizle'));
    await tester.pump();
    expect(_isObscured(tester, 'login_password'), isTrue);
  });

  testWidgets('after an expired session an info banner explains why', (
    tester,
  ) async {
    // Stored tokens that the backend no longer accepts.
    final api = FakeAuthApi()
      ..meError = apiError('AUTH_INVALID_TOKEN', status: 401);
    final app = await TestApp.create(
      api: api,
      tokens: InMemoryTokenStore(
        const AuthTokens(accessToken: 'old', refreshToken: 'old'),
      ),
    );
    await tester.pumpWidget(app.screen(const LoginScreen()));
    await tester.pumpAndSettle();

    expect(
      find.text('Oturum süren doldu. Lütfen tekrar giriş yap.'),
      findsOneWidget,
    );
  });

  testWidgets('the button is disabled while the request runs', (tester) async {
    final gate = Completer<void>();
    final api = FakeAuthApi()
      ..passwords['ebru@example.com'] = 'Parola123'
      ..loginGate = gate;
    final app = await TestApp.create(api: api);
    await tester.pumpWidget(app.screen(const LoginScreen()));

    await _type(tester, 'login_email', 'ebru@example.com');
    await _type(tester, 'login_password', 'Parola123');
    await tester.tap(find.widgetWithText(FilledButton, 'Giriş yap'));
    await tester.pump(); // request started, not finished

    final button = tester.widget<FilledButton>(find.byType(FilledButton));
    expect(button.onPressed, isNull);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    gate.complete();
    await tester.pumpAndSettle();
    expect(api.loginCalls, 1);
  });

  testWidgets('submitting hides the keyboard (the focus is released)', (
    tester,
  ) async {
    final app = await TestApp.create();
    await tester.pumpWidget(app.screen(const LoginScreen()));
    await tester.tap(find.byKey(const Key('login_email')));
    await tester.pump();
    expect(FocusManager.instance.primaryFocus, isNotNull);

    await _submit(tester);

    final focused = FocusManager.instance.primaryFocus;
    expect(
      focused?.context?.findAncestorWidgetOfExactType<EditableText>(),
      isNull,
      reason:
          'no text field may keep the focus (and the keyboard) after submit',
    );
  });
}
