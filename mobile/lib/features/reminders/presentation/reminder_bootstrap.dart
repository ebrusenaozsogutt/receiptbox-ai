import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/data_changed.dart';
import '../../auth/domain/auth_state.dart';
import '../../auth/presentation/auth_controller.dart';
import '../data/notification_gateway.dart';
import '../data/reminder_prefs.dart';
import '../data/reminder_sync.dart';

/// Wires the reminders into the app's life (P13), above the router:
/// - signed in → set up notifications, ask once (explanation screen) on Android 13+, sync;
/// - the app comes back to the foreground → sync;
/// - a write succeeded on the backend → sync (debounced);
/// - signed out → cancel this account's notifications;
/// - a notification is tapped (also when it started the app) → open its screen.
class ReminderBootstrap extends ConsumerStatefulWidget {
  const ReminderBootstrap({
    super.key,
    required this.router,
    required this.child,
  });

  final GoRouter router;
  final Widget child;

  @override
  ConsumerState<ReminderBootstrap> createState() => _ReminderBootstrapState();
}

class _ReminderBootstrapState extends ConsumerState<ReminderBootstrap> {
  late final AppLifecycleListener _lifecycle;
  bool _started = false;

  bool get _signedIn =>
      ref.read(authProvider).status == AuthStatus.authenticated;

  @override
  void initState() {
    super.initState();
    _lifecycle = AppLifecycleListener(onResume: _onResume);
    ref.listenManual<AuthState>(
      authProvider,
      (previous, next) => _onAuth(previous?.status, next.status),
      fireImmediately: true,
    );
    ref.listenManual<int>(dataChangedSignalProvider, (_, _) {
      if (_signedIn) ref.read(reminderSyncProvider).requestSync();
    });
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    super.dispose();
  }

  void _onResume() {
    if (_signedIn) ref.read(reminderSyncProvider).sync();
  }

  Future<void> _onAuth(AuthStatus? previous, AuthStatus next) async {
    if (next == AuthStatus.authenticated &&
        previous != AuthStatus.authenticated) {
      await _start();
    } else if (next == AuthStatus.unauthenticated &&
        previous == AuthStatus.authenticated) {
      await ref.read(reminderSyncProvider).clear();
    }
  }

  Future<void> _start() async {
    final gateway = ref.read(notificationGatewayProvider);
    try {
      if (!_started) {
        await gateway.initialize(_open);
        _started = true;
        final payload = await gateway.launchPayload();
        if (payload != null) _open(payload);
      }
      final prefs = ref.read(reminderPrefsProvider);
      if (!prefs.introSeen && !await gateway.notificationsEnabled()) {
        widget.router.push('/notifications/intro');
      }
    } on Object {
      // No notification support on this device: the app works without reminders.
    }
    await ref.read(reminderSyncProvider).sync();
  }

  /// A tapped notification: its screen on top of Home, so "back" stays in the app.
  void _open(String? route) {
    if (route == null || !route.startsWith('/') || !_signedIn) return;
    final router = widget.router;
    if (router.state.matchedLocation != '/home') router.go('/home');
    router.push(route);
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
