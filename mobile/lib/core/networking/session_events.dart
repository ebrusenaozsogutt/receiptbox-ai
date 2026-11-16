import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'session_events.g.dart';

/// Raised by the network layer when the backend ends the session (refresh token rejected).
/// The auth feature listens to it and sends the user back to the login screen.
/// (A signal provider keeps core/ from depending on features/.)
@Riverpod(keepAlive: true)
class SessionExpiredSignal extends _$SessionExpiredSignal {
  @override
  int build() => 0;

  void signal() => state++;
}
