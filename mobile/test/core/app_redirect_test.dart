import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/app.dart';
import 'package:receiptbox/features/auth/domain/auth_state.dart';
import 'package:receiptbox/features/auth/domain/user_profile.dart';

final _user = UserProfile(
  id: 'u1',
  email: 'a@b.c',
  isAdultConfirmed: true,
  createdAt: DateTime(2026, 11, 16),
);

String? _go(
  AuthState auth,
  String location, {
  bool consentSeen = true,
  bool hasAccount = true,
}) => appRedirect(
  auth: auth,
  consentSeen: consentSeen,
  hasAccount: hasAccount,
  location: location,
);

void main() {
  group('while the stored session is being checked', () {
    test('everything goes to the splash screen', () {
      expect(_go(const AuthState.checking(), '/home'), '/splash');
      expect(_go(const AuthState.checking(), '/login'), '/splash');
      expect(_go(const AuthState.checking(), '/splash'), isNull);
    });

    test(
      'an unreachable server also keeps the splash (with its retry button)',
      () {
        expect(_go(const AuthState.unreachable('x'), '/home'), '/splash');
        expect(_go(const AuthState.unreachable('x'), '/splash'), isNull);
      },
    );
  });

  group('first run: consent comes before anything else', () {
    test('goes to the consent screen', () {
      const signedOut = AuthState.unauthenticated();
      expect(_go(signedOut, '/register', consentSeen: false), '/consent');
      expect(_go(signedOut, '/login', consentSeen: false), '/consent');
      expect(_go(signedOut, '/consent', consentSeen: false), isNull);
    });
  });

  group('signed out', () {
    const signedOut = AuthState.unauthenticated();

    test('a device that never had an account starts at Register', () {
      expect(_go(signedOut, '/consent', hasAccount: false), '/register');
      expect(_go(signedOut, '/home', hasAccount: false), '/register');
    });

    test('a device with an account (or after logout) goes to Login', () {
      expect(_go(signedOut, '/home'), '/login');
      expect(_go(signedOut, '/settings'), '/login');
      expect(_go(signedOut, '/consent'), '/login');
    });

    test('Login and Register stay reachable from each other', () {
      expect(_go(signedOut, '/login'), isNull);
      expect(_go(signedOut, '/register'), isNull);
      expect(_go(signedOut, '/login', hasAccount: false), isNull);
    });

    test('an expired session also lands on Login', () {
      expect(
        _go(const AuthState.unauthenticated(sessionExpired: true), '/home'),
        '/login',
      );
    });
  });

  group('signed in', () {
    final signedIn = AuthState.authenticated(_user);

    test('the pre-session pages lead to Home', () {
      for (final page in ['/splash', '/consent', '/login', '/register']) {
        expect(_go(signedIn, page), '/home', reason: page);
      }
    });

    test('app pages are left alone', () {
      for (final page in [
        '/home',
        '/transactions',
        '/products',
        '/assistant',
        '/settings',
        '/capture/scan',
        '/products/new',
      ]) {
        expect(_go(signedIn, page), isNull, reason: page);
      }
    });
  });
}
