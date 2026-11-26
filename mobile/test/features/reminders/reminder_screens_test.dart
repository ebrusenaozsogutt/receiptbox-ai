import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/features/analytics/presentation/budgets_screen.dart';
import 'package:receiptbox/features/installments/presentation/installment_schedule_screen.dart';
import 'package:receiptbox/features/products/presentation/product_detail_screen.dart';
import 'package:receiptbox/features/reminders/domain/notification_plan.dart';
import 'package:receiptbox/features/reminders/domain/reminder_models.dart';

import '../../support/fakes.dart';
import '../../support/product_fakes.dart';
import '../../support/settings_helpers.dart';

Future<TestApp> start(
  WidgetTester tester, {
  bool notificationsAllowed = true,
  void Function(TestApp app)? before,
  TestApp? app,
}) async {
  final testApp = app ?? await TestApp.signedIn();
  testApp.notifications.enabled = notificationsAllowed;
  before?.call(testApp);
  await tester.pumpWidget(testApp.app());
  await tester.pumpAndSettle();
  return testApp;
}

Future<void> openSettings(WidgetTester tester) async {
  await tester.tap(find.byTooltip('Ayarlar'));
  await tester.pumpAndSettle();
  await scrollSettingsTo(tester, find.text('BİLDİRİMLER'));
}

Reminder warrantyIn(TestApp app, Duration ahead) => Reminder(
  id: 'w-1',
  type: ReminderType.warrantyExpiry,
  fireAt: app.now.add(ahead),
  daysBefore: 30,
  productId: 'p-1',
  productName: 'AirPods',
);

void main() {
  group('asking for the permission (Android 13+)', () {
    testWidgets('the explanation comes first, then the system dialog', (
      tester,
    ) async {
      final app = await start(tester, notificationsAllowed: false);

      expect(find.text('Son günleri kaçırma'), findsOneWidget);
      expect(app.notifications.permissionRequests, 0);

      await tester.tap(find.byKey(const Key('notifications_allow')));
      await tester.pumpAndSettle();

      expect(app.notifications.permissionRequests, 1);
      expect(find.text('Son günleri kaçırma'), findsNothing);
      expect(find.byKey(const Key('home_list')), findsOneWidget);
    });

    testWidgets('"Şimdi değil" does not ask, and the screen never comes back', (
      tester,
    ) async {
      final app = await start(tester, notificationsAllowed: false);

      await tester.tap(find.byKey(const Key('notifications_later')));
      await tester.pumpAndSettle();
      expect(app.notifications.permissionRequests, 0);
      expect(find.byKey(const Key('home_list')), findsOneWidget);

      await tester.pumpWidget(const SizedBox()); // kill the app
      await start(tester, notificationsAllowed: false, app: app);
      expect(find.text('Son günleri kaçırma'), findsNothing);
    });

    testWidgets('not shown when notifications are already allowed', (
      tester,
    ) async {
      await start(tester);
      expect(find.text('Son günleri kaçırma'), findsNothing);
    });

    testWidgets('Settings offers the permission again when it is off', (
      tester,
    ) async {
      final app = await start(
        tester,
        notificationsAllowed: false,
        before: (app) =>
            app.preferences.setBool('notifications_intro_seen', true),
      );
      await openSettings(tester);

      expect(find.text('Bildirimler kapalı'), findsOneWidget);
      await tester.tap(
        find.byKey(const Key('notifications_permission_button')),
      );
      await tester.pumpAndSettle();

      expect(app.notifications.permissionRequests, 1);
      expect(find.text('Bildirimler kapalı'), findsNothing);
    });
  });

  group('sync', () {
    testWidgets('signing in schedules the upcoming reminders', (tester) async {
      final app = await start(
        tester,
        before: (app) =>
            app.reminders.items = [warrantyIn(app, const Duration(days: 3))],
      );

      final pending = app.notifications.pending[notificationIdFor('w-1')]!;
      expect(
        pending.body,
        "AirPods'un garanti süresinin bitmesine 30 gün kaldı.",
      );
      expect(pending.payload, '/products/p-1');
    });

    testWidgets('restarting the app many times adds no duplicate', (
      tester,
    ) async {
      final app = await start(
        tester,
        before: (app) =>
            app.reminders.items = [warrantyIn(app, const Duration(days: 3))],
      );
      for (var i = 0; i < 3; i++) {
        await tester.pumpWidget(const SizedBox());
        await start(tester, app: app);
      }

      expect(app.notifications.pending, hasLength(1));
      expect(app.notifications.shown, isEmpty);
    });
  });

  group('tapping a notification', () {
    testWidgets('a warranty opens its product', (tester) async {
      final app = await start(
        tester,
        before: (app) => app.products.products.add(fakeProduct()),
      );

      app.notifications.onTap!('/products/p-1');
      await tester.pumpAndSettle();

      expect(find.byType(ProductDetailScreen), findsOneWidget);
    });

    testWidgets('a budget opens Bütçeler; back returns to Home', (
      tester,
    ) async {
      final app = await start(tester);

      app.notifications.onTap!('/budgets');
      await tester.pumpAndSettle();
      expect(find.byType(BudgetsScreen), findsOneWidget);

      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('home_list')), findsOneWidget);
    });

    testWidgets('a notification that started the app opens its screen', (
      tester,
    ) async {
      await start(
        tester,
        before: (app) => app.notifications.launch = '/installments',
      );

      expect(find.byType(InstallmentScheduleScreen), findsOneWidget);
    });
  });

  group('Settings', () {
    testWidgets('a switch per kind, stored on the device; off cancels', (
      tester,
    ) async {
      final app = await start(
        tester,
        before: (app) =>
            app.reminders.items = [warrantyIn(app, const Duration(days: 3))],
      );
      expect(app.notifications.pending, hasLength(1));
      await openSettings(tester);

      for (final kind in ReminderKind.values) {
        final tile = find.byKey(Key('notifications_${kind.name}'));
        expect(tile, findsOneWidget);
        expect(
          find.descendant(of: tile, matching: find.text(kind.label)),
          findsOneWidget,
        );
      }
      await tester.tap(find.byKey(const Key('notifications_warranty')));
      await tester.pumpAndSettle();

      expect(app.preferences.getBool('notifications_warranty'), isFalse);
      expect(app.notifications.pending, isEmpty);
    });

    testWidgets('exact alarms: shown as off with a button to turn them on', (
      tester,
    ) async {
      final app = await start(tester);
      await openSettings(tester);
      await scrollSettingsTo(
        tester,
        find.byKey(const Key('notifications_exact_tile')),
      );

      expect(find.textContaining('birkaç dakika gecikebilir'), findsOneWidget);
      await tester.tap(find.byKey(const Key('notifications_exact_button')));
      await tester.pumpAndSettle();
      expect(app.notifications.exactRequests, 1);
    });

    testWidgets('debug: "Bütçe" schedules a notification to /budgets', (
      tester,
    ) async {
      final app = await start(tester);
      await openSettings(tester);
      final button = find.byKey(const Key('debug_notify_budget'));
      await scrollSettingsTo(tester, button);

      await tester.tap(button);
      await tester.pumpAndSettle();

      final pending = app
          .notifications
          .pending[debugNotificationIdFor(ReminderKind.budget)]!;
      expect(pending.payload, '/budgets');
      expect(find.textContaining('2 dakika sonra gelecek'), findsOneWidget);
    });

    testWidgets('debug: a warranty needs a product', (tester) async {
      final app = await start(tester);
      await openSettings(tester);
      final button = find.byKey(const Key('debug_notify_warranty'));
      await scrollSettingsTo(tester, button);

      await tester.tap(button);
      await tester.pumpAndSettle();
      expect(find.text('Önce bir ürün ekle.'), findsOneWidget);
      expect(app.notifications.pending, isEmpty);

      app.products.products.add(fakeProduct());
      await tester.tap(button);
      await tester.pumpAndSettle();
      expect(
        app
            .notifications
            .pending[debugNotificationIdFor(ReminderKind.warranty)]!
            .payload,
        '/products/p-1',
      );
    });
  });
}
