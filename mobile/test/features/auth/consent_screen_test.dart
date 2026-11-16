import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/features/auth/presentation/consent_screen.dart';

import '../../support/fakes.dart';

void main() {
  testWidgets('explains OCR, masking, the AI provider, storage and deletion', (
    tester,
  ) async {
    final app = await TestApp.create();
    await tester.pumpWidget(app.screen(const ConsentScreen()));

    // Spec 15.3: on-device OCR, masking, external AI provider, what is stored, how to delete.
    expect(find.text('Verilerin senin kontrolünde'), findsOneWidget);
    expect(find.text('Fişin telefonunda okunur'), findsOneWidget);
    expect(find.text('Kişisel bilgiler gizlenir'), findsOneWidget);
    expect(find.text('Yapay zekâ maskelenmiş metni işler'), findsOneWidget);
    expect(find.text('Neler saklanır?'), findsOneWidget);
    expect(find.text('Silmek senin elinde'), findsOneWidget);
    expect(find.textContaining('maskelenir'), findsWidgets);
    expect(find.textContaining('hiçbir zaman çıkmaz'), findsOneWidget);
  });

  testWidgets('"Kabul ediyorum" stores the consent and AI use', (tester) async {
    final app = await TestApp.create();
    await tester.pumpWidget(app.screen(const ConsentScreen()));

    await tester.tap(find.text('Kabul ediyorum'));
    await tester.pumpAndSettle();

    expect(app.preferences.getBool('consent_seen'), isTrue);
    expect(app.preferences.getBool('ai_consent'), isTrue);
  });

  testWidgets('"Şimdilik kabul etmiyorum" finishes the screen with AI off', (
    tester,
  ) async {
    final app = await TestApp.create();
    await tester.pumpWidget(app.screen(const ConsentScreen()));

    await tester.tap(find.text('Şimdilik kabul etmiyorum'));
    await tester.pumpAndSettle();

    expect(app.preferences.getBool('consent_seen'), isTrue);
    expect(app.preferences.getBool('ai_consent'), isFalse);
  });

  testWidgets('says that declining means manual entry only', (tester) async {
    final app = await TestApp.create();
    await tester.pumpWidget(app.screen(const ConsentScreen()));

    expect(find.textContaining('elle girebilirsin'), findsOneWidget);
  });
}
