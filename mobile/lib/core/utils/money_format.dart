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
