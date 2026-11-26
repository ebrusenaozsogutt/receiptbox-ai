import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/core/networking/data_changed.dart';
import 'package:receiptbox/features/assistant/domain/assistant_models.dart';
import 'package:receiptbox/features/installments/presentation/installment_schedule_screen.dart';
import 'package:receiptbox/features/products/presentation/product_detail_screen.dart';
import 'package:receiptbox/features/settings/presentation/settings_screen.dart';
import 'package:receiptbox/features/transactions/presentation/transaction_detail_screen.dart';

import '../../support/fakes.dart';
import '../../support/product_fakes.dart';

Future<TestApp> openAssistant(
  WidgetTester tester, {
  bool consent = true,
  void Function(TestApp app)? before,
}) async {
  final app = await TestApp.signedIn();
  await app.preferences.setBool('ai_consent', consent);
  app.notifications.enabled =
      true; // no notification explanation screen in the way
  before?.call(app);
  await tester.pumpWidget(app.app());
  await tester.pumpAndSettle();
  await tester.tap(find.text('Asistan').last);
  await tester.pumpAndSettle();
  return app;
}

Future<void> askChip(WidgetTester tester, int index) async {
  await tester.ensureVisible(find.byKey(Key('assistant_chip_$index')));
  await tester.pump();
  await tester.tap(find.byKey(Key('assistant_chip_$index')));
  await tester.pumpAndSettle();
}

Future<void> type(WidgetTester tester, String question) async {
  await tester.enterText(find.byKey(const Key('assistant_input')), question);
  await tester.tap(find.byKey(const Key('assistant_send')));
  await tester.pumpAndSettle();
}

const marketAnswer = 'Bu ay markete 1.549,90 TL harcadın.';

void main() {
  group('AI consent', () {
    testWidgets('without it the tab explains why and links to Settings', (
      tester,
    ) async {
      final app = await openAssistant(tester, consent: false);

      expect(find.text('Asistan kapalı'), findsOneWidget);
      expect(find.byKey(const Key('assistant_input')), findsNothing);
      await tester.tap(find.byKey(const Key('assistant_open_settings')));
      await tester.pumpAndSettle();
      expect(find.byType(SettingsScreen), findsOneWidget);
      expect(app.assistant.questions, isEmpty);
    });

    testWidgets('a consent refused by the server is explained in the chat', (
      tester,
    ) async {
      final app = await openAssistant(
        tester,
        before: (app) => app.assistant.fail('AI_CONSENT_REQUIRED'),
      );

      await askChip(tester, 0);

      expect(
        find.text(
          "Asistan için yapay zekâ izni gerekiyor. Ayarlar'dan açabilirsin.",
        ),
        findsOneWidget,
      );
      expect(app.assistant.questions, hasLength(1));
    });
  });

  testWidgets('the five suggested questions; a chip asks its question', (
    tester,
  ) async {
    final app = await openAssistant(
      tester,
      before: (app) => app.assistant.reply(marketAnswer),
    );

    for (var i = 0; i < suggestedQuestions.length; i++) {
      expect(
        find.descendant(
          of: find.byKey(Key('assistant_chip_$i')),
          matching: find.text(suggestedQuestions[i]),
        ),
        findsOneWidget,
      );
    }
    expect(suggestedQuestions, [
      'Bu ay markete ne kadar harcadım?',
      'Garantisi bitecek ürünler?',
      'Kalan taksitlerim ne kadar?',
      'En pahalı 5 alışverişim?',
      'Kulaklığın faturası nerede?',
    ]);

    await askChip(tester, 0);

    expect(app.assistant.questions, ['Bu ay markete ne kadar harcadım?']);
    expect(find.text('Bu ay markete ne kadar harcadım?'), findsOneWidget);
    expect(find.text(marketAnswer), findsOneWidget);
    expect(find.byKey(const Key('assistant_chip_0')), findsNothing);
  });

  testWidgets('typing indicator while waiting; the input is locked', (
    tester,
  ) async {
    final app = await openAssistant(tester);
    app.assistant
      ..gate = Completer<void>()
      ..reply('Tamam.');

    await tester.enterText(find.byKey(const Key('assistant_input')), 'Selam');
    await tester.tap(find.byKey(const Key('assistant_send')));
    await tester.pump();

    expect(find.byKey(const Key('assistant_typing')), findsOneWidget);
    final input = tester.widget<TextField>(
      find.byKey(const Key('assistant_input')),
    );
    expect(input.enabled, isFalse);

    app.assistant.gate!.complete();
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('assistant_typing')), findsNothing);
    expect(find.text('Tamam.'), findsOneWidget);
  });

  testWidgets('earlier answered questions go along as history', (tester) async {
    final app = await openAssistant(tester);
    app.assistant
      ..reply(marketAnswer)
      ..reply('Geçen ay 1.000,00 TL.');

    await askChip(tester, 0);
    await type(tester, 'Peki geçen ay?');

    expect(app.assistant.histories.last.single.question, suggestedQuestions[0]);
    expect(app.assistant.histories.last.single.reply!.answer, marketAnswer);
  });

  testWidgets('an unavailable assistant: message and "Tekrar dene"', (
    tester,
  ) async {
    final app = await openAssistant(tester);
    app.assistant
      ..fail('ASSISTANT_UNAVAILABLE')
      ..reply(marketAnswer);

    await askChip(tester, 0);
    expect(
      find.text('Asistan şu an yanıt veremiyor. Biraz sonra tekrar dene.'),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const Key('assistant_retry')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('assistant_error')), findsNothing);
    expect(find.text(marketAnswer), findsOneWidget);
    expect(app.assistant.questions, [
      suggestedQuestions[0],
      suggestedQuestions[0],
    ]);
  });

  group('action buttons open the screen with the numbers', () {
    testWidgets('OPEN_TRANSACTIONS sets the filters and opens Harcamalar', (
      tester,
    ) async {
      await openAssistant(
        tester,
        before: (app) => app.assistant.reply(
          'Bu ay Migros\'a 1.349,90 TL ödedin.',
          actions: const [
            AssistantAction(
              type: AssistantActionType.openTransactions,
              label: 'Harcamaları gör',
              params: {
                'from': '2026-11-01',
                'to': '2026-11-30',
                'category': 'GROCERY',
                'q': 'migros',
              },
            ),
          ],
        ),
      );
      await askChip(tester, 0);

      await tester.tap(find.byKey(const Key('assistant_action_0')));
      await tester.pumpAndSettle();

      final search = tester.widget<TextField>(
        find.byKey(const Key('search_field')),
      );
      expect(search.controller!.text, 'migros');
      final category = find.byKey(const Key('filter_category'));
      expect(
        find.descendant(of: category, matching: find.text('Market')),
        findsOneWidget,
      );
    });

    testWidgets('OPEN_PRODUCT opens the product card', (tester) async {
      await openAssistant(
        tester,
        before: (app) {
          app.products.products.add(fakeProduct());
          app.assistant.reply(
            'AirPods Pro: garantisi 20 gün sonra bitiyor.',
            actions: const [
              AssistantAction(
                type: AssistantActionType.openProduct,
                label: 'AirPods Pro kartı',
                params: {'id': 'p-1'},
              ),
            ],
          );
        },
      );
      await askChip(tester, 1);

      await tester.tap(find.byKey(const Key('assistant_action_0')));
      await tester.pumpAndSettle();

      expect(find.byType(ProductDetailScreen), findsOneWidget);
    });

    testWidgets('OPEN_INSTALLMENTS opens Taksitler at the month', (
      tester,
    ) async {
      await openAssistant(
        tester,
        before: (app) => app.assistant.reply(
          'Kalan taksitlerinin toplamı 30.000,00 TL.',
          actions: const [
            AssistantAction(
              type: AssistantActionType.openInstallments,
              label: 'Taksitleri gör',
              params: {'month': '2026-12'},
            ),
          ],
        ),
      );
      await askChip(tester, 2);

      await tester.tap(find.byKey(const Key('assistant_action_0')));
      await tester.pumpAndSettle();

      final screen = tester.widget<InstallmentScheduleScreen>(
        find.byType(InstallmentScheduleScreen),
      );
      expect(screen.focusMonth, '2026-12');
    });

    testWidgets('OPEN_DOCUMENT opens the document viewer', (tester) async {
      await openAssistant(
        tester,
        before: (app) => app.assistant.reply(
          'AirPods Pro için bir fatura kayıtlı.',
          actions: const [
            AssistantAction(
              type: AssistantActionType.openDocument,
              label: 'Fiş görüntüsü aç',
              // An image: pdfx cannot render on the Linux CI runner; this test is about routing.
              params: {'id': 'doc-1', 'pdf': 'false'},
            ),
          ],
        ),
      );
      await askChip(tester, 4);

      await tester.tap(find.byKey(const Key('assistant_action_0')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      final viewer = tester.widget<DocumentViewerScreen>(
        find.byType(DocumentViewerScreen),
      );
      expect((viewer.documentId, viewer.isPdf), ('doc-1', false));
    });
  });

  testWidgets(
    '"Geçmişi temizle" asks, deletes on the server, empties the chat',
    (tester) async {
      final app = await openAssistant(
        tester,
        before: (app) => app.assistant.reply(marketAnswer),
      );
      await askChip(tester, 0);

      await tester.tap(find.byKey(const Key('assistant_clear')));
      await tester.pumpAndSettle();
      expect(find.text('Geçmiş silinsin mi?'), findsOneWidget);
      await tester.tap(find.byKey(const Key('assistant_clear_confirm')));
      await tester.pumpAndSettle();

      expect(app.assistant.clearCalls, 1);
      expect(find.text(marketAnswer), findsNothing);
      expect(find.byKey(const Key('assistant_chip_0')), findsOneWidget);
      expect(find.text('Geçmiş silindi.'), findsOneWidget);
    },
  );

  testWidgets('the chat survives switching tabs', (tester) async {
    await openAssistant(
      tester,
      before: (app) => app.assistant.reply(marketAnswer),
    );
    await askChip(tester, 0);

    await tester.tap(find.text('Ana Sayfa').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Asistan').last);
    await tester.pumpAndSettle();

    expect(find.text(marketAnswer), findsOneWidget);
  });

  group('models and networking', () {
    test('an unknown action type is dropped, the rest is read', () {
      final reply = AssistantReply.fromJson({
        'answer': 'x',
        'actions': [
          {'type': 'OPEN_SOMETHING_NEW', 'label': 'a', 'params': {}},
          {
            'type': 'OPEN_PRODUCT',
            'label': 'Kart',
            'params': {'id': 'p-1'},
          },
        ],
        'tool_calls': [
          {'name': 'search_products', 'args': {}},
        ],
      });

      expect(reply.actions.single.type, AssistantActionType.openProduct);
      expect(reply.actions.single.params, {'id': 'p-1'});
      expect(reply.tools, ['search_products']);
    });

    test('a question does not trigger the reminder sync', () {
      var changes = 0;
      final interceptor = DataChangedInterceptor(() => changes++);
      void respond(Map<String, dynamic> extra) => interceptor.onResponse(
        Response<void>(
          requestOptions: RequestOptions(
            path: '/x',
            method: 'POST',
            extra: extra,
          ),
          statusCode: 200,
        ),
        ResponseInterceptorHandler(),
      );

      respond({DataChangedInterceptor.ignoreKey: true});
      expect(changes, 0);
      respond({});
      expect(changes, 1);
    });
  });
}
