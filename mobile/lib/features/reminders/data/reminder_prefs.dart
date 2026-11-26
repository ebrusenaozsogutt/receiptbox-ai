import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../core/storage/settings_store.dart';
import '../domain/reminder_models.dart';

part 'reminder_prefs.g.dart';

/// Local notification settings (P13): one switch per kind, whether the explanation screen was
/// shown, and which reminders this phone already scheduled or showed. No personal data: only
/// reminder ids.
class ReminderPrefs {
  const ReminderPrefs(this._prefs);

  final SharedPreferences _prefs;

  static const _introSeenKey = 'notifications_intro_seen';
  static const _handledKey = 'reminders_handled';
  static String _enabledKey(ReminderKind kind) => 'notifications_${kind.name}';

  /// Every kind is on until the user switches it off.
  bool isEnabled(ReminderKind kind) =>
      _prefs.getBool(_enabledKey(kind)) ?? true;

  Set<ReminderKind> get enabledKinds => {
    for (final kind in ReminderKind.values)
      if (isEnabled(kind)) kind,
  };

  Future<void> setEnabled(ReminderKind kind, bool value) =>
      _prefs.setBool(_enabledKey(kind), value);

  bool get introSeen => _prefs.getBool(_introSeenKey) ?? false;

  Future<void> setIntroSeen() => _prefs.setBool(_introSeenKey, true);

  Set<String> get handled =>
      (_prefs.getStringList(_handledKey) ?? const []).toSet();

  Future<void> setHandled(Set<String> ids) =>
      _prefs.setStringList(_handledKey, ids.toList()..sort());

  /// Signed out: the next account starts clean.
  Future<void> clearHandled() => _prefs.remove(_handledKey);
}

@Riverpod(keepAlive: true)
ReminderPrefs reminderPrefs(Ref ref) =>
    ReminderPrefs(ref.watch(sharedPreferencesProvider));

/// The Settings switches, reactive.
@Riverpod(keepAlive: true)
class NotificationKinds extends _$NotificationKinds {
  @override
  Set<ReminderKind> build() => ref.read(reminderPrefsProvider).enabledKinds;

  Future<void> set(ReminderKind kind, bool value) async {
    await ref.read(reminderPrefsProvider).setEnabled(kind, value);
    state = ref.read(reminderPrefsProvider).enabledKinds;
  }
}
