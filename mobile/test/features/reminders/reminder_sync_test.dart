import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/features/reminders/data/reminder_prefs.dart';
import 'package:receiptbox/features/reminders/data/reminder_sync.dart';
import 'package:receiptbox/features/reminders/domain/notification_plan.dart';
import 'package:receiptbox/features/reminders/domain/reminder_models.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/reminder_fakes.dart';

final start = DateTime.utc(2026, 11, 26, 9);

Reminder warranty(String id, DateTime at) => Reminder(
  id: id,
  type: ReminderType.warrantyExpiry,
  fireAt: at,
  daysBefore: 30,
  productId: 'p-$id',
  productName: 'AirPods',
);

class Harness {
  Harness(this.prefs);

  final SharedPreferences prefs;
  final api = FakeRemindersApi();
  final gateway = FakeNotificationGateway();
  DateTime now = start;

  late final sync = ReminderSync(
    api: api,
    gateway: gateway,
    prefs: ReminderPrefs(prefs),
    clock: () => now,
  );

  static Future<Harness> create() async {
    SharedPreferences.setMockInitialValues({});
    return Harness(await SharedPreferences.getInstance());
  }
}

void main() {
  test('schedules every upcoming reminder under its stable id', () async {
    final h = await Harness.create();
    h.api.items = [
      warranty('a', start.add(const Duration(days: 3))),
      warranty('b', start.add(const Duration(days: 9))),
    ];

    final outcome = await h.sync.sync();

    expect(outcome!.scheduled, 2);
    expect(h.gateway.pending.keys.toSet(), {
      notificationIdFor('a'),
      notificationIdFor('b'),
    });
    expect(h.gateway.pending[notificationIdFor('a')]!.payload, '/products/p-a');
  });

  test('many resumes in a row create no duplicates', () async {
    final h = await Harness.create();
    h.api.items = [
      warranty('a', start.add(const Duration(days: 3))),
      warranty('b', start.add(const Duration(days: 9))),
    ];

    for (var i = 0; i < 5; i++) {
      await h.sync.sync();
    }

    expect(h.gateway.pending, hasLength(2));
    expect(h.gateway.shown, isEmpty);
  });

  test('a moved deadline replaces the old notification', () async {
    final h = await Harness.create();
    h.api.items = [warranty('old', start.add(const Duration(days: 3)))];
    await h.sync.sync();

    // The backend recomputed: the old reminder is gone, a new one exists.
    h.api.items = [warranty('new', start.add(const Duration(days: 40)))];
    await h.sync.sync();

    expect(h.gateway.pending.keys, [notificationIdFor('new')]);
    expect(
      h.gateway.pending.values.single.at,
      start.add(const Duration(days: 40)),
    );
  });

  test(
    'a returned product (no reminders any more) leaves nothing pending',
    () async {
      final h = await Harness.create();
      h.api.items = [warranty('a', start.add(const Duration(days: 3)))];
      await h.sync.sync();

      h.api.items = [];
      await h.sync.sync();

      expect(h.gateway.pending, isEmpty);
    },
  );

  test('a fired notification is not shown again on the next resume', () async {
    final h = await Harness.create();
    h.api.items = [warranty('a', start.add(const Duration(minutes: 2)))];
    await h.sync.sync();

    h.now = start.add(const Duration(minutes: 3));
    h.gateway.fireDue(h.now);
    await h.sync.sync();
    await h.sync.sync();

    expect(h.gateway.shown, hasLength(1));
    expect(h.gateway.pending, isEmpty);
  });

  test('a budget reached a moment ago is shown once', () async {
    final h = await Harness.create();
    h.api.items = [
      Reminder(
        id: 'bud',
        type: ReminderType.budget80,
        fireAt: start.subtract(const Duration(minutes: 1)),
      ),
    ];

    await h.sync.sync();
    await h.sync.sync();

    expect(h.gateway.shown, hasLength(1));
    expect(h.gateway.shown.single.payload, '/budgets');
  });

  test('a due reminder waits while notifications are not allowed', () async {
    // Found on the emulator: the first sync ran while the permission dialog was still open;
    // the budget notification was dropped by Android but remembered as shown.
    final h = await Harness.create();
    h.gateway.enabled = false;
    h.api.items = [
      Reminder(
        id: 'bud',
        type: ReminderType.budget80,
        fireAt: start.subtract(const Duration(minutes: 1)),
      ),
    ];

    await h.sync.sync();
    expect(h.gateway.shown, isEmpty);

    h.gateway.enabled = true; // the user tapped "Allow"
    await h.sync.sync();
    expect(h.gateway.shown, hasLength(1));
  });

  test('the debug notifications survive a sync', () async {
    final h = await Harness.create();
    await h.gateway.schedule(
      id: debugNotificationIdFor(ReminderKind.budget),
      title: 'Bütçe (deneme)',
      body: 'x',
      at: start.add(const Duration(minutes: 2)),
      payload: '/budgets',
      exact: false,
    );

    await h.sync.sync();

    expect(h.gateway.pending.keys, [
      debugNotificationIdFor(ReminderKind.budget),
    ]);
  });

  test('exact alarms are used only when allowed', () async {
    final h = await Harness.create();
    h.api.items = [warranty('a', start.add(const Duration(days: 3)))];

    await h.sync.sync();
    expect(h.gateway.pending.values.single.exact, isFalse);

    h.gateway.exactAllowed = true;
    await h.sync.sync();
    expect(h.gateway.pending.values.single.exact, isTrue);
  });

  test('offline: what is scheduled stays scheduled', () async {
    final h = await Harness.create();
    h.api.items = [warranty('a', start.add(const Duration(days: 3)))];
    await h.sync.sync();

    h.api.offline = true;
    expect(await h.sync.sync(), isNull);
    expect(h.gateway.pending, hasLength(1));
  });

  test('a kind switched off is cancelled at the next sync', () async {
    final h = await Harness.create();
    h.api.items = [warranty('a', start.add(const Duration(days: 3)))];
    await h.sync.sync();

    await ReminderPrefs(h.prefs).setEnabled(ReminderKind.warranty, false);
    await h.sync.sync();

    expect(h.gateway.pending, isEmpty);
  });

  test('signing out cancels this account\'s notifications', () async {
    final h = await Harness.create();
    h.api.items = [warranty('a', start.add(const Duration(days: 3)))];
    await h.sync.sync();

    await h.sync.clear();

    expect(h.gateway.pending, isEmpty);
    expect(ReminderPrefs(h.prefs).handled, isEmpty);
  });

  test(
    'syncs asked for while one runs end in one more run, not in parallel',
    () async {
      final h = await Harness.create();
      h.api.items = [warranty('a', start.add(const Duration(days: 3)))];

      await Future.wait([h.sync.sync(), h.sync.sync(), h.sync.sync()]);

      expect(h.api.calls, lessThanOrEqualTo(2));
      expect(h.gateway.pending, hasLength(1));
    },
  );
}
