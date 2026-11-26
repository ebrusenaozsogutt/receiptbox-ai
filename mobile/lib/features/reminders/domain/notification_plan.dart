import 'reminder_models.dart';
import 'reminder_texts.dart';

/// Notification ids below this are reserved for the debug "2 dakika sonra bildir" buttons;
/// reminder ids are mapped above it, so a sync never cancels a debug notification.
const firstReminderNotificationId = 1000;
const _maxNotificationId = 0x7fffffff; // Android ids are signed 32-bit integers

/// A stable notification id for a reminder id (FNV-1a, 32 bit). The same reminder always gets
/// the same id, so scheduling it again replaces it instead of adding a second notification.
int notificationIdFor(String reminderId) {
  var hash = 0x811c9dc5;
  for (final unit in reminderId.codeUnits) {
    hash ^= unit;
    hash = (hash * 0x01000193) & 0xffffffff;
  }
  return firstReminderNotificationId +
      hash % (_maxNotificationId - firstReminderNotificationId);
}

/// The debug notification of a kind (ids 1–4).
int debugNotificationIdFor(ReminderKind kind) => kind.index + 1;

class PlannedNotification {
  const PlannedNotification({
    required this.id,
    required this.reminderId,
    required this.fireAt,
    required this.message,
  });

  final int id;
  final String reminderId;
  final DateTime fireAt;
  final ReminderMessage message;
}

class NotificationPlan {
  const NotificationPlan({
    required this.schedule,
    required this.showNow,
    required this.handled,
  });

  /// In the future: handed to the system alarm.
  final List<PlannedNotification> schedule;

  /// Already due (e.g. a budget reached a moment ago) and never shown on this phone.
  final List<PlannedNotification> showNow;

  /// The reminder ids this phone has scheduled or shown, to remember for the next sync.
  final Set<String> handled;
}

/// What to do with the reminders from the backend. Pure, so the "no duplicates" rule is
/// testable:
/// - a reminder of a kind switched off in Settings is not scheduled;
/// - a future one is scheduled (under its stable id);
/// - a due one is shown once if this phone never scheduled or showed it, else skipped (the
///   system already showed it when its time came);
/// - only the ids still listed by the backend are remembered.
NotificationPlan planNotifications({
  required List<Reminder> reminders,
  required DateTime now,
  required Set<ReminderKind> enabled,
  required Set<String> handled,
}) {
  final schedule = <PlannedNotification>[];
  final showNow = <PlannedNotification>[];
  final remembered = <String>{};
  for (final reminder in reminders) {
    final wasHandled = handled.contains(reminder.id);
    if (!enabled.contains(reminder.type.kind)) {
      if (wasHandled) remembered.add(reminder.id);
      continue;
    }
    final planned = PlannedNotification(
      id: notificationIdFor(reminder.id),
      reminderId: reminder.id,
      fireAt: reminder.fireAt,
      message: messageFor(reminder),
    );
    if (reminder.fireAt.isAfter(now)) {
      schedule.add(planned);
      remembered.add(reminder.id);
    } else if (!wasHandled) {
      showNow.add(planned);
      remembered.add(reminder.id);
    } else {
      remembered.add(reminder.id);
    }
  }
  return NotificationPlan(
    schedule: schedule,
    showNow: showNow,
    handled: remembered,
  );
}
