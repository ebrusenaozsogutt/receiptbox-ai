import 'dart:async';

import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../domain/notification_plan.dart';
import '../domain/reminder_models.dart';
import 'notification_gateway.dart';
import 'reminder_prefs.dart';
import 'reminders_api.dart';

part 'reminder_sync.g.dart';

/// What one sync did (for tests and the debug log; no personal data).
class SyncOutcome {
  const SyncOutcome({
    required this.scheduled,
    required this.shown,
    required this.cancelled,
  });

  final int scheduled;
  final int shown;
  final int cancelled;
}

/// Keeps the phone's notifications equal to the backend's reminders (spec 12, P13):
/// every pending ReceiptBox notification is cancelled and the reminders from
/// `GET /reminders/upcoming` are scheduled again under their stable ids, so running it any
/// number of times (start, resume, after every change) never creates a duplicate. The debug
/// notifications (ids below [firstReminderNotificationId]) are left alone.
class ReminderSync {
  ReminderSync({
    required this.api,
    required this.gateway,
    required this.prefs,
    required this.clock,
  });

  final RemindersApi api;
  final NotificationGateway gateway;
  final ReminderPrefs prefs;
  final DateTime Function() clock;

  Future<SyncOutcome?>? _running;
  bool _again = false;
  Timer? _debounce;

  /// Runs now; a call during a running sync makes it run once more afterwards.
  Future<SyncOutcome?> sync() {
    final running = _running;
    if (running != null) {
      _again = true;
      return running;
    }
    final future = _loop();
    _running = future;
    return future.whenComplete(() => _running = null);
  }

  /// Many writes in a row (e.g. a bank import) end in one sync.
  void requestSync({Duration delay = const Duration(milliseconds: 800)}) {
    _debounce?.cancel();
    _debounce = Timer(delay, sync);
  }

  Future<SyncOutcome?> _loop() async {
    SyncOutcome? outcome;
    do {
      _again = false;
      outcome = await _once();
    } while (_again);
    return outcome;
  }

  Future<SyncOutcome?> _once() async {
    final List<Reminder> reminders;
    try {
      reminders = await api.upcoming();
    } on Object {
      // Offline or signed out: keep what is scheduled; the next start or resume tries again.
      return null;
    }
    final plan = planNotifications(
      reminders: reminders,
      now: clock(),
      enabled: prefs.enabledKinds,
      handled: prefs.handled,
    );
    final exact = await gateway.canScheduleExact();
    var cancelled = 0;
    for (final id in await gateway.pendingIds()) {
      if (id >= firstReminderNotificationId) {
        await gateway.cancel(id);
        cancelled++;
      }
    }
    for (final item in plan.schedule) {
      await gateway.schedule(
        id: item.id,
        title: item.message.title,
        body: item.message.body,
        at: item.fireAt,
        payload: item.message.route,
        exact: exact,
      );
    }
    for (final item in plan.showNow) {
      await gateway.show(
        id: item.id,
        title: item.message.title,
        body: item.message.body,
        payload: item.message.route,
      );
    }
    await prefs.setHandled(plan.handled);
    return SyncOutcome(
      scheduled: plan.schedule.length,
      shown: plan.showNow.length,
      cancelled: cancelled,
    );
  }

  /// Signed out: no reminder of this account may fire on the phone any more.
  Future<void> clear() async {
    _debounce?.cancel();
    try {
      for (final id in await gateway.pendingIds()) {
        if (id >= firstReminderNotificationId) await gateway.cancel(id);
      }
    } on Object {
      // Nothing scheduled or no notification support: nothing to clear.
    }
    await prefs.clearHandled();
  }

  void dispose() => _debounce?.cancel();
}

/// The clock of the reminders (tests replace it).
@Riverpod(keepAlive: true)
DateTime Function() reminderClock(Ref ref) => DateTime.now;

@Riverpod(keepAlive: true)
ReminderSync reminderSync(Ref ref) {
  final sync = ReminderSync(
    api: ref.watch(remindersApiProvider),
    gateway: ref.watch(notificationGatewayProvider),
    prefs: ref.watch(reminderPrefsProvider),
    clock: ref.watch(reminderClockProvider),
  );
  ref.onDispose(sync.dispose);
  return sync;
}
