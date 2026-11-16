/// Client-side form checks. They give instant feedback only; the backend stays the authority
/// (same rules as backend/app/services/auth.py) and its answer is shown if it disagrees.
library;

const passwordMinLength = 8;
const passwordMaxLength = 128;
const emailMaxLength = 254;

final _emailPattern = RegExp(
  r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$",
);

/// Returns an error message, or null when the e-mail looks valid.
String? validateEmail(String? value) {
  final email = (value ?? '').trim();
  if (email.isEmpty) return 'E-posta adresini gir.';
  if (email.length > emailMaxLength || !_emailPattern.hasMatch(email)) {
    return 'Geçerli bir e-posta adresi gir.';
  }
  return null;
}

/// Login only needs a non-empty password (old passwords must keep working).
String? validateLoginPassword(String? value) {
  if (value == null || value.isEmpty) return 'Parolanı gir.';
  return null;
}

/// Registration rules: 8-128 characters, at least one letter and one digit.
String? validateNewPassword(String? value) {
  final password = value ?? '';
  if (password.isEmpty) return 'Bir parola belirle.';
  if (password.length < passwordMinLength) {
    return 'Parola en az $passwordMinLength karakter olmalı.';
  }
  if (password.length > passwordMaxLength) {
    return 'Parola en fazla $passwordMaxLength karakter olabilir.';
  }
  if (!RegExp(r'\p{L}', unicode: true).hasMatch(password)) {
    return 'Parola en az bir harf içermeli.';
  }
  if (!RegExp(r'\d').hasMatch(password)) {
    return 'Parola en az bir rakam içermeli.';
  }
  return null;
}

const adultConfirmationMessage =
    'Devam etmek için 18 yaşından büyük olduğunu onaylamalısın.';

String? validateAdultConfirmed(bool? value) =>
    value == true ? null : adultConfirmationMessage;
