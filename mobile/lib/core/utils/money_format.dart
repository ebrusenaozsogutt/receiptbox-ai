/// Money is an `int` of minor units (kuruş), never a double (project rule).
/// These helpers turn it into Turkish text: 134990 -> "1.349,90" / "1.349,90 TL".
library;

/// "1.349,90" (no currency). Integer arithmetic only, so there are no rounding surprises.
String formatMoneyMinor(int minor) {
  final sign = minor < 0 ? '-' : '';
  final absolute = minor.abs();
  final lira = absolute ~/ 100;
  final kurus = absolute % 100;
  final grouped = lira.toString().replaceAllMapped(
    RegExp(r'\B(?=(\d{3})+(?!\d))'),
    (_) => '.',
  );
  return '$sign$grouped,${kurus.toString().padLeft(2, '0')}';
}

/// "1.349,90 TL" — the way amounts are shown everywhere in the app.
String formatMoneyTl(int minor) => '${formatMoneyMinor(minor)} TL';

/// "5.420 TL": whole lira, halves rounded up (the category list and the change chip of the home
/// screen, as in the Figma frame). Display only: the stored amount keeps its kuruş.
String formatMoneyWholeTl(int minor) {
  final sign = minor < 0 ? '-' : '';
  final lira = (minor.abs() + 50) ~/ 100;
  final grouped = lira.toString().replaceAllMapped(
    RegExp(r'\B(?=(\d{3})+(?!\d))'),
    (_) => '.',
  );
  return '$sign$grouped TL';
}

/// What the user typed ("494,60", "494.60", "1.349,90 TL", "1349") as minor units, or null when
/// it is not a usable amount. Same rules as the backend's money parser: a lone separator followed
/// by exactly three digits is a thousands separator ("1.349" = 1349 TL, "1,349" is refused as
/// ambiguous), more than two decimals or a minus sign are refused.
int? parseMoneyToMinor(String input) {
  final cleaned = input
      .replaceAll(RegExp('(₺|TL|TRY)', caseSensitive: false), '')
      .replaceAll(RegExp(r'[\s ]'), '');
  if (cleaned.isEmpty || !RegExp(r'^[0-9.,]+$').hasMatch(cleaned)) return null;

  final lastComma = cleaned.lastIndexOf(',');
  final lastDot = cleaned.lastIndexOf('.');
  var integerText = cleaned;
  var fraction = '';
  if (lastComma >= 0 && lastDot >= 0) {
    // The separator that comes last is the decimal one, the other must group thousands.
    final decimalAt = lastComma > lastDot ? lastComma : lastDot;
    final thousands = lastComma > lastDot ? '.' : ',';
    integerText = cleaned.substring(0, decimalAt);
    fraction = cleaned.substring(decimalAt + 1);
    if (!_isGrouped(integerText, thousands)) return null;
    integerText = integerText.replaceAll(thousands, '');
  } else if (lastComma >= 0) {
    if (cleaned.indexOf(',') != lastComma) {
      return null; // "1,349,00" and the like
    }
    integerText = cleaned.substring(0, lastComma);
    fraction = cleaned.substring(lastComma + 1);
    if (fraction.length == 3 && integerText.isNotEmpty) {
      return null; // "1,349": ambiguous
    }
  } else if (lastDot >= 0) {
    final after = cleaned.substring(lastDot + 1);
    final single = cleaned.indexOf('.') == lastDot;
    if (single && after.isNotEmpty && after.length <= 2) {
      integerText = cleaned.substring(0, lastDot);
      fraction = after;
    } else if (_isGrouped(cleaned, '.')) {
      integerText = cleaned.replaceAll('.', '');
    } else {
      return null;
    }
  }

  if (integerText.isEmpty) integerText = '0';
  if (!RegExp(r'^[0-9]+$').hasMatch(integerText) || integerText.length > 12) {
    return null;
  }
  if (fraction.length > 2 ||
      (fraction.isNotEmpty && !RegExp(r'^[0-9]+$').hasMatch(fraction))) {
    return null;
  }
  final kurus = fraction.isEmpty ? 0 : int.parse(fraction.padRight(2, '0'));
  return int.parse(integerText) * 100 + kurus;
}

bool _isGrouped(String text, String separator) {
  final escaped = RegExp.escape(separator);
  return RegExp('^[0-9]{1,3}($escaped[0-9]{3})+\$').hasMatch(text) ||
      RegExp(r'^[0-9]+$').hasMatch(text);
}
