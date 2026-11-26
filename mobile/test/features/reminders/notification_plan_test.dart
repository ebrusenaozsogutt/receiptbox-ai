import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/features/reminders/domain/notification_plan.dart';
import 'package:receiptbox/features/reminders/domain/reminder_models.dart';
import 'package:receiptbox/features/transactions/domain/spending_category.dart';

final now = DateTime.utc(2026, 11, 26, 9);

Reminder reminder(
  String id, {
  ReminderType type = ReminderType.warrantyExpiry,
  Duration fromNow = const Duration(days: 3),
}) => Reminder(
  id: id,
  type: type,
  fireAt: now.add(fromNow),
  daysBefore: 30,
  productId: 'p-1',
  productName: 'AirPods',
  merchant: 'Teknosa',
  category: SpendingCategory.grocery,
);

NotificationPlan plan(
  List<Reminder> reminders, {
  Set<ReminderKind> enabled = const {...ReminderKind.values},
  Set<String> handled = const {},
}) => planNotifications(
  reminders: reminders,
  now: now,
  enabled: enabled,
  handled: handled,
);

void main() {
  group('notification ids', () {
    test('the same reminder always gets the same id', () {
      const id = '3f2b8c1e-8d4a-4c0e-9b8e-0f1d2c3b4a59';
      expect(notificationIdFor(id), notificationIdFor(id));
    });

    test('are above the debug ids and fit a signed 32-bit integer', () {
      for (var i = 0; i < 2000; i++) {
        final id = notificationIdFor('reminder-$i');
        expect(id, greaterThanOrEqualTo(firstReminderNotificationId));
        expect(id, lessThanOrEqualTo(0x7fffffff));
      }
    });

    test('different reminders get different ids (no collision in 2000)', () {
      final ids = {
        for (var i = 0; i < 2000; i++) notificationIdFor('reminder-$i'),
      };
      expect(ids, hasLength(2000));
    });

    test('debug ids are 1-4, below every reminder id', () {
      expect(
        [for (final kind in ReminderKind.values) debugNotificationIdFor(kind)],
        [1, 2, 3, 4],
      );
    });
  });

  group('the plan', () {
    test('a future reminder is scheduled under its stable id', () {
      final result = plan([reminder('a')]);

      expect(result.schedule.single.id, notificationIdFor('a'));
      expect(result.schedule.single.fireAt, now.add(const Duration(days: 3)));
      expect(result.schedule.single.message.route, '/products/p-1');
      expect(result.showNow, isEmpty);
      expect(result.handled, {'a'});
    });

    test('a due reminder never handled here is shown now, once', () {
      final due = reminder(
        'b',
        type: ReminderType.budget80,
        fromNow: const Duration(minutes: -5),
      );

      final first = plan([due]);
      final second = plan([due], handled: first.handled);

      expect(
        first.showNow.single.message.body,
        "Market bütçenin %80'ine ulaştın.",
      );
      expect(second.showNow, isEmpty);
      expect(second.schedule, isEmpty);
    });

    test('a scheduled reminder whose time passed is not shown again', () {
      final r = reminder('c', fromNow: const Duration(hours: 1));
      final before = plan([r]);
      final later = planNotifications(
        reminders: [r],
        now: now.add(const Duration(hours: 2)),
        enabled: {...ReminderKind.values},
        handled: before.handled,
      );

      expect(later.showNow, isEmpty);
      expect(later.schedule, isEmpty);
      expect(later.handled, {'c'});
    });

    test('a kind switched off in Settings is not scheduled', () {
      final result = plan(
        [reminder('w'), reminder('r', type: ReminderType.returnDeadline)],
        enabled: {ReminderKind.returnWindow},
      );

      expect([for (final s in result.schedule) s.reminderId], ['r']);
    });

    test('only the reminders still listed are remembered', () {
      final result = plan([reminder('a')], handled: {'a', 'gone'});

      expect(result.handled, {'a'});
    });

    test('planning again gives the same notifications (no duplicates)', () {
      final reminders = [
        reminder('a'),
        reminder('b', type: ReminderType.returnDeadline),
        reminder('c', type: ReminderType.installmentEnd),
      ];
      final first = plan(reminders);
      final again = plan(reminders, handled: first.handled);

      List<int> ids(NotificationPlan p) => [for (final s in p.schedule) s.id];
      expect(ids(again), ids(first));
      expect(ids(first).toSet(), hasLength(3));
    });
  });
}
