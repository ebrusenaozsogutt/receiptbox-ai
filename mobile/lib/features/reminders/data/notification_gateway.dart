import 'package:flutter/services.dart' show PlatformException;
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:timezone/data/latest.dart' as tz_data;
import 'package:timezone/timezone.dart' as tz;

part 'notification_gateway.g.dart';

/// Everything the app asks of the phone's notification system (P13). The widget tests replace
/// it with a fake, so no platform channel is needed there.
abstract interface class NotificationGateway {
  /// Set up once; [onTap] receives the payload (a route) of a tapped notification.
  Future<void> initialize(void Function(String? payload) onTap);

  /// The payload of the notification that started the app, if any.
  Future<String?> launchPayload();

  /// Notifications allowed (always true below Android 13 unless the user turned them off).
  Future<bool> notificationsEnabled();

  /// The Android 13+ system dialog. Returns whether notifications are allowed afterwards.
  Future<bool> requestPermission();

  /// Exact alarms allowed (Android 14 denies them by default).
  Future<bool> canScheduleExact();

  /// Opens the system page where the user can allow exact alarms.
  Future<void> requestExactAlarms();

  /// Ids of the notifications waiting for their time.
  Future<List<int>> pendingIds();

  Future<void> cancel(int id);

  /// At [at] (an instant). Exact when [exact] and allowed, otherwise inexact; never throws
  /// because exact alarms are refused.
  Future<void> schedule({
    required int id,
    required String title,
    required String body,
    required DateTime at,
    required String payload,
    required bool exact,
  });

  Future<void> show({
    required int id,
    required String title,
    required String body,
    required String payload,
  });
}

const _channelId = 'receiptbox_reminders';

/// The whole text stays readable when the notification is expanded.
NotificationDetails _details(String body) => NotificationDetails(
  android: AndroidNotificationDetails(
    _channelId,
    'Hatırlatmalar',
    channelDescription: 'Garanti, iade, son taksit ve bütçe hatırlatmaları',
    importance: Importance.high,
    priority: Priority.high,
    styleInformation: BigTextStyleInformation(body),
  ),
);

class PluginNotificationGateway implements NotificationGateway {
  PluginNotificationGateway([FlutterLocalNotificationsPlugin? plugin])
    : _plugin = plugin ?? FlutterLocalNotificationsPlugin();

  final FlutterLocalNotificationsPlugin _plugin;
  bool _initialized = false;

  AndroidFlutterLocalNotificationsPlugin? get _android => _plugin
      .resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin
      >();

  @override
  Future<void> initialize(void Function(String? payload) onTap) async {
    if (_initialized) return;
    tz_data.initializeTimeZones();
    tz.setLocalLocation(tz.getLocation('Europe/Istanbul'));
    await _plugin.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('ic_stat_receipt'),
      ),
      onDidReceiveNotificationResponse: (response) => onTap(response.payload),
    );
    _initialized = true;
  }

  @override
  Future<String?> launchPayload() async {
    final details = await _plugin.getNotificationAppLaunchDetails();
    if (details == null || !details.didNotificationLaunchApp) return null;
    return details.notificationResponse?.payload;
  }

  @override
  Future<bool> notificationsEnabled() async =>
      await _android?.areNotificationsEnabled() ?? false;

  @override
  Future<bool> requestPermission() async =>
      await _android?.requestNotificationsPermission() ?? false;

  @override
  Future<bool> canScheduleExact() async {
    try {
      return await _android?.canScheduleExactNotifications() ?? false;
    } on PlatformException {
      return false;
    }
  }

  @override
  Future<void> requestExactAlarms() async {
    try {
      await _android?.requestExactAlarmsPermission();
    } on PlatformException {
      // Some phones have no such settings page: the reminders stay inexact.
    }
  }

  @override
  Future<List<int>> pendingIds() async => [
    for (final request in await _plugin.pendingNotificationRequests())
      request.id,
  ];

  @override
  Future<void> cancel(int id) => _plugin.cancel(id: id);

  @override
  Future<void> schedule({
    required int id,
    required String title,
    required String body,
    required DateTime at,
    required String payload,
    required bool exact,
  }) async {
    final when = tz.TZDateTime.from(at, tz.local);
    Future<void> scheduleWith(AndroidScheduleMode mode) =>
        _plugin.zonedSchedule(
          id: id,
          title: title,
          body: body,
          scheduledDate: when,
          notificationDetails: _details(body),
          androidScheduleMode: mode,
          payload: payload,
        );
    if (exact) {
      try {
        await scheduleWith(AndroidScheduleMode.exactAllowWhileIdle);
        return;
      } on PlatformException {
        // The permission was taken back in the meantime: fall back to inexact.
      }
    }
    await scheduleWith(AndroidScheduleMode.inexactAllowWhileIdle);
  }

  @override
  Future<void> show({
    required int id,
    required String title,
    required String body,
    required String payload,
  }) => _plugin.show(
    id: id,
    title: title,
    body: body,
    notificationDetails: _details(body),
    payload: payload,
  );
}

@Riverpod(keepAlive: true)
NotificationGateway notificationGateway(Ref ref) => PluginNotificationGateway();
