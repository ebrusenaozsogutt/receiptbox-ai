import 'package:receiptbox/core/networking/api_error.dart';
import 'package:receiptbox/features/reminders/data/notification_gateway.dart';
import 'package:receiptbox/features/reminders/data/reminders_api.dart';
import 'package:receiptbox/features/reminders/domain/reminder_models.dart';

/// The backend's upcoming reminders, settable per test.
class FakeRemindersApi implements RemindersApi {
  List<Reminder> items = [];
  int calls = 0;
  bool offline = false;

  @override
  Future<List<Reminder>> upcoming({int days = 60}) async {
    calls++;
    if (offline) {
      throw const ApiError(
        code: 'NETWORK_UNREACHABLE',
        message: 'Bağlantı yok.',
      );
    }
    return List.of(items);
  }
}

class FakeNotification {
  const FakeNotification({
    required this.id,
    required this.title,
    required this.body,
    required this.payload,
    this.at,
    this.exact,
  });

  final int id;
  final String title;
  final String body;
  final String payload;

  /// Null for a notification shown at once.
  final DateTime? at;
  final bool? exact;
}

/// The phone's notification system: what is pending, what was shown, the permissions.
class FakeNotificationGateway implements NotificationGateway {
  bool enabled = true;
  bool exactAllowed = false;
  bool grantOnRequest = true;
  int permissionRequests = 0;
  int exactRequests = 0;
  String? launch;
  void Function(String? payload)? onTap;

  final Map<int, FakeNotification> pending = {};
  final List<FakeNotification> shown = [];

  @override
  Future<void> initialize(void Function(String? payload) onTap) async {
    this.onTap = onTap;
  }

  @override
  Future<String?> launchPayload() async => launch;

  @override
  Future<bool> notificationsEnabled() async => enabled;

  @override
  Future<bool> requestPermission() async {
    permissionRequests++;
    if (grantOnRequest) enabled = true;
    return enabled;
  }

  @override
  Future<bool> canScheduleExact() async => exactAllowed;

  @override
  Future<void> requestExactAlarms() async {
    exactRequests++;
  }

  @override
  Future<List<int>> pendingIds() async => pending.keys.toList();

  @override
  Future<void> cancel(int id) async {
    pending.remove(id);
  }

  @override
  Future<void> schedule({
    required int id,
    required String title,
    required String body,
    required DateTime at,
    required String payload,
    required bool exact,
  }) async {
    pending[id] = FakeNotification(
      id: id,
      title: title,
      body: body,
      payload: payload,
      at: at,
      exact: exact,
    );
  }

  @override
  Future<void> show({
    required int id,
    required String title,
    required String body,
    required String payload,
  }) async {
    shown.add(
      FakeNotification(id: id, title: title, body: body, payload: payload),
    );
  }

  /// The system fires every pending notification due at [now] (it disappears from pending).
  void fireDue(DateTime now) {
    final due = pending.values.where((n) => !n.at!.isAfter(now)).toList();
    for (final n in due) {
      pending.remove(n.id);
      shown.add(n);
    }
  }
}
