import 'user_profile.dart';

enum AuthStatus {
  /// Start-up: looking at stored tokens and asking the backend who we are.
  checking,
  authenticated,
  unauthenticated,

  /// Tokens exist but the backend could not be reached. The user stays signed in
  /// (a bad network must not log anyone out) and can retry.
  unreachable,
}

class AuthState {
  const AuthState._(
    this.status, {
    this.user,
    this.sessionExpired = false,
    this.message,
  });

  const AuthState.checking() : this._(AuthStatus.checking);
  const AuthState.authenticated(UserProfile user)
    : this._(AuthStatus.authenticated, user: user);
  const AuthState.unauthenticated({bool sessionExpired = false})
    : this._(AuthStatus.unauthenticated, sessionExpired: sessionExpired);
  const AuthState.unreachable(String message)
    : this._(AuthStatus.unreachable, message: message);

  final AuthStatus status;
  final UserProfile? user;

  /// True when the user was signed out because the backend ended the session.
  final bool sessionExpired;

  /// Turkish message for [AuthStatus.unreachable].
  final String? message;
}
