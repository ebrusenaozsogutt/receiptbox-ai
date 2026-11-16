import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/features/auth/domain/validators.dart';
import 'package:receiptbox/features/auth/presentation/register_screen.dart';

import '../../support/fakes.dart';

const _goodPassword = 'Parola123';

Future<void> _fill(
  WidgetTester tester, {
  String email = 'ebru@example.com',
  String password = _goodPassword,
}) async {
  await tester.enterText(find.byKey(const Key('register_email')), email);
  await tester.enterText(find.byKey(const Key('register_password')), password);
}

Future<void> _submit(WidgetTester tester) async {
  final button = find.widgetWithText(FilledButton, 'Kayıt ol');
  await tester.ensureVisible(button);
  await tester.tap(button);
  await tester.pumpAndSettle();
}

Future<void> _tickAdult(WidgetTester tester) async {
  final box = find.byType(Checkbox);
  await tester.ensureVisible(box);
  await tester.tap(box);
  await tester.pump();
}

void main() {
  testWidgets('the 18+ checkbox starts unticked', (tester) async {
    final app = await TestApp.create();
    await tester.pumpWidget(app.screen(const RegisterScreen()));

    expect(tester.widget<Checkbox>(find.byType(Checkbox)).value, isFalse);
    expect(
      find.text('18 yaşından büyük olduğumu onaylıyorum.'),
      findsOneWidget,
    );
  });

  testWidgets(
    'without the 18+ tick registering is blocked and nothing is sent',
    (tester) async {
      final app = await TestApp.create();
      await tester.pumpWidget(app.screen(const RegisterScreen()));

      await _fill(tester);
      await _submit(tester);

      expect(find.text(adultConfirmationMessage), findsOneWidget);
      expect(app.api.registerCalls, 0);
      expect(app.tokens.tokens, isNull);
    },
  );

  testWidgets('with the 18+ tick the account is created', (tester) async {
    final app = await TestApp.create();
    await tester.pumpWidget(app.screen(const RegisterScreen()));

    await _fill(tester);
    await _tickAdult(tester);
    await _submit(tester);

    expect(app.api.registerCalls, 1);
    expect(app.api.lastIsAdultConfirmed, isTrue);
    expect(find.text(adultConfirmationMessage), findsNothing);
    expect(app.tokens.tokens, isNotNull);
  });

  testWidgets('tapping the sentence also ticks the box', (tester) async {
    final app = await TestApp.create();
    await tester.pumpWidget(app.screen(const RegisterScreen()));

    final sentence = find.text('18 yaşından büyük olduğumu onaylıyorum.');
    await tester.ensureVisible(sentence);
    await tester.tap(sentence);
    await tester.pump();

    expect(tester.widget<Checkbox>(find.byType(Checkbox)).value, isTrue);
  });

  testWidgets('unticking again brings the error back on submit', (
    tester,
  ) async {
    final app = await TestApp.create();
    await tester.pumpWidget(app.screen(const RegisterScreen()));
    await _fill(tester);
    await _tickAdult(tester);
    await _tickAdult(tester); // off again

    await _submit(tester);

    expect(find.text(adultConfirmationMessage), findsOneWidget);
    expect(app.api.registerCalls, 0);
  });

  group('password rules are explained before sending', () {
    final cases = {
      'abc1': 'Parola en az 8 karakter olmalı.',
      'abcdefgh': 'Parola en az bir rakam içermeli.',
      '12345678': 'Parola en az bir harf içermeli.',
    };
    for (final entry in cases.entries) {
      testWidgets('"${entry.key}" -> ${entry.value}', (tester) async {
        final app = await TestApp.create();
        await tester.pumpWidget(app.screen(const RegisterScreen()));

        await _fill(tester, password: entry.key);
        await _tickAdult(tester);
        await _submit(tester);

        expect(find.text(entry.value), findsOneWidget);
        expect(app.api.registerCalls, 0);
      });
    }
  });

  testWidgets('an invalid e-mail is rejected before sending', (tester) async {
    final app = await TestApp.create();
    await tester.pumpWidget(app.screen(const RegisterScreen()));

    await _fill(tester, email: 'nope');
    await _tickAdult(tester);
    await _submit(tester);

    expect(find.text('Geçerli bir e-posta adresi gir.'), findsOneWidget);
    expect(app.api.registerCalls, 0);
  });

  testWidgets('an e-mail that is taken shows the server error in Turkish', (
    tester,
  ) async {
    final api = FakeAuthApi()..passwords['ebru@example.com'] = 'Baska-parola1';
    final app = await TestApp.create(api: api);
    await tester.pumpWidget(app.screen(const RegisterScreen()));

    await _fill(tester);
    await _tickAdult(tester);
    await _submit(tester);

    expect(
      find.text(
        'Bu e-posta adresiyle zaten bir hesap var. Giriş yapmayı dene.',
      ),
      findsOneWidget,
    );
    expect(app.tokens.tokens, isNull);
  });

  testWidgets('the password hint states the rules', (tester) async {
    final app = await TestApp.create();
    await tester.pumpWidget(app.screen(const RegisterScreen()));

    expect(
      find.text('En az 8 karakter, bir harf ve bir rakam'),
      findsOneWidget,
    );
  });
}
