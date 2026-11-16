import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/features/auth/domain/validators.dart';

void main() {
  group('validateEmail', () {
    test('accepts normal addresses (and trims spaces)', () {
      for (final email in [
        'ebru@example.com',
        'first.last+tag@sub.example.co.uk',
        '  ebru@example.com ',
        "o'brien@example.org",
      ]) {
        expect(validateEmail(email), isNull, reason: email);
      }
    });

    test('asks for an address when empty', () {
      expect(validateEmail(''), 'E-posta adresini gir.');
      expect(validateEmail('   '), 'E-posta adresini gir.');
      expect(validateEmail(null), 'E-posta adresini gir.');
    });

    test('rejects malformed addresses', () {
      for (final email in [
        'abc',
        'a@b',
        '@x.com',
        'a b@x.com',
        'a@x..com',
        'ünal@x.com',
      ]) {
        expect(
          validateEmail(email),
          'Geçerli bir e-posta adresi gir.',
          reason: email,
        );
      }
    });
  });

  group('validateNewPassword (same rules as the backend)', () {
    test('accepts 8-128 characters with a letter and a digit', () {
      for (final password in [
        'abcdefg1',
        'Parola123',
        'ş1ifre-uzun',
        'a' * 127 + '1',
      ]) {
        expect(validateNewPassword(password), isNull, reason: password);
      }
    });

    test('says what is missing', () {
      expect(validateNewPassword(''), 'Bir parola belirle.');
      expect(validateNewPassword('abc1'), 'Parola en az 8 karakter olmalı.');
      expect(
        validateNewPassword('abcdefgh'),
        'Parola en az bir rakam içermeli.',
      );
      expect(
        validateNewPassword('12345678'),
        'Parola en az bir harf içermeli.',
      );
      expect(
        validateNewPassword('!!!!!!!!'),
        'Parola en az bir harf içermeli.',
      );
      expect(
        validateNewPassword('a1' * 65),
        'Parola en fazla 128 karakter olabilir.',
      );
    });
  });

  group('validateLoginPassword', () {
    test(
      'only requires something to be typed (old passwords must keep working)',
      () {
        expect(validateLoginPassword(''), 'Parolanı gir.');
        expect(validateLoginPassword(null), 'Parolanı gir.');
        expect(validateLoginPassword('x'), isNull);
      },
    );
  });

  group('validateAdultConfirmed', () {
    test('must be ticked', () {
      expect(validateAdultConfirmed(false), adultConfirmationMessage);
      expect(validateAdultConfirmed(null), adultConfirmationMessage);
      expect(validateAdultConfirmed(true), isNull);
    });
  });
}
