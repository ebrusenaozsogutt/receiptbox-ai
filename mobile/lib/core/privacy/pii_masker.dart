/// On-device masking of personal data (spec 15.1). Runs BEFORE any text leaves the phone.
///
/// Rules, in this order:
/// 1. lines about balances/limits/account numbers are replaced as a whole  -> [BALANCE]
/// 2. names after "Sayın", "Ad Soyad", "Kart Sahibi", "Müşteri"            -> [NAME]
/// 3. e-mail addresses                                                      -> [EMAIL]
/// 4. IBAN (TR + 24 digits, also partly starred)                            -> [IBAN]
/// 5. card numbers (13-19 digits passing Luhn, and partly starred forms)    -> [CARD]
/// 6. TCKN (11 digits passing the official checksum)                        -> [TCKN]
/// 7. Turkish phone numbers (+90 / 0090 / 0xxx / 5xx)                       -> [PHONE]
///
/// The masker is deliberately biased towards masking: a wrongly masked number costs a little
/// readability, a missed one leaks personal data. Receipt totals, dates and times are left
/// alone (they never match the patterns above).
///
/// Only COUNTS per type are returned besides the text (for metrics). The text that goes in is
/// never stored or logged by this class.
library;

enum PiiType {
  iban('[IBAN]'),
  card('[CARD]'),
  tckn('[TCKN]'),
  phone('[PHONE]'),
  email('[EMAIL]'),
  balance('[BALANCE]'),
  name('[NAME]');

  const PiiType(this.token);

  /// The text that replaces the personal data.
  final String token;
}

class MaskResult {
  const MaskResult(this.text, this.counts);

  /// The masked text. Safe to send to the backend.
  final String text;

  /// How many items of each type were masked (types with zero are absent).
  final Map<PiiType, int> counts;

  int get total => counts.values.fold(0, (sum, count) => sum + count);
}

class PiiMasker {
  const PiiMasker();

  MaskResult mask(String input) {
    final counts = <PiiType, int>{};
    void count(PiiType type) => counts[type] = (counts[type] ?? 0) + 1;

    final lines = input
        .replaceAll('\r\n', '\n')
        .replaceAll('\r', '\n')
        .split('\n');
    final masked = <String>[];
    var maskNextLine = false; // a name label stood alone on the previous line

    for (final line in lines) {
      final folded = foldForMatching(line);

      // 1. Balance / limit / account-number lines go away completely.
      if (_balanceLine.hasMatch(folded)) {
        masked.add(PiiType.balance.token);
        count(PiiType.balance);
        maskNextLine = false;
        continue;
      }

      // 2. Names.
      if (maskNextLine && line.trim().isNotEmpty) {
        masked.add(PiiType.name.token);
        count(PiiType.name);
        maskNextLine = false;
        continue;
      }
      var current = line;
      final label = _nameLabel.firstMatch(folded);
      if (label != null) {
        final labelEnd = label.end;
        final remainderFolded = folded.substring(labelEnd);
        final remainder = _stripSeparators(remainderFolded);
        if (remainder.isEmpty) {
          maskNextLine = true; // the name is on the next line
        } else if (!_notAName.hasMatch(remainder)) {
          final separatorLength =
              remainderFolded.length -
              remainderFolded.replaceFirst(_leadingSeparators, '').length;
          final keep = line.substring(0, labelEnd + separatorLength);
          current =
              '$keep${separatorLength == 0 ? ' ' : ''}${PiiType.name.token}';
          count(PiiType.name);
          masked.add(current);
          continue;
        }
      }

      // 3-7. Inline patterns, most specific first.
      current = _replace(current, _email, PiiType.email, count);
      current = _replace(current, _iban, PiiType.iban, count);
      current = _replace(current, _phoneInternational, PiiType.phone, count);
      current = _replace(
        current,
        _cardPartial,
        PiiType.card,
        count,
        accept: _hasHiddenDigits,
      );
      current = _replace(
        current,
        _cardNumber,
        PiiType.card,
        count,
        accept: _isLuhnCard,
      );
      current = _replace(
        current,
        _tckn,
        PiiType.tckn,
        count,
        accept: _isValidTckn,
      );
      current = _replace(
        current,
        _phoneLocal,
        PiiType.phone,
        count,
        accept: _notATaxNumber,
      );
      masked.add(current);
    }

    return MaskResult(masked.join('\n'), Map.unmodifiable(counts));
  }

  // ---- text helpers ------------------------------------------------------------------------

  /// Lower-case, ASCII-like copy of [text] with the SAME length, used only to find keywords:
  /// "Kullanılabilir", "KULLANILABİLİR" and "Kullanilabilir" (OCR dropped the dots) all
  /// become "kullanilabilir". (Dart's own toLowerCase would turn İ into two characters.)
  static String foldForMatching(String text) {
    final out = StringBuffer();
    for (final unit in text.codeUnits) {
      final char = String.fromCharCode(unit);
      out.write(switch (char) {
        'İ' || 'I' || 'ı' || 'i' => 'i',
        'Ş' || 'ş' => 's',
        'Ğ' || 'ğ' => 'g',
        'Ü' || 'ü' => 'u',
        'Ö' || 'ö' => 'o',
        'Ç' || 'ç' => 'c',
        _ => char.toLowerCase(),
      });
    }
    return out.toString();
  }

  static final _leadingSeparators = RegExp(r'^[\s:;\-–.,]+');

  static String _stripSeparators(String text) =>
      text.replaceFirst(_leadingSeparators, '').trim();

  static String _replace(
    String text,
    RegExp pattern,
    PiiType type,
    void Function(PiiType) count, {
    bool Function(String match, String before)? accept,
  }) {
    return text.replaceAllMapped(pattern, (match) {
      final found = match.group(0)!;
      if (accept != null && !accept(found, text.substring(0, match.start))) {
        return found;
      }
      count(type);
      return type.token;
    });
  }

  // ---- patterns ----------------------------------------------------------------------------

  // Folded (see foldForMatching), so they match with or without Turkish letters.
  static final _balanceLine = RegExp(
    r'\bbakiye(?:si|niz)?\b|\bkullanilabilir\b|\blimit(?:i|iniz|leri|ler)?\b|'
    r'\btoplam borc\b|\bhesap (?:no|numarasi)\b',
  );
  static final _nameLabel = RegExp(
    r'\b(?:sayin|ad soyad|adi soyadi|kart sahibi|musteri)\b',
  );

  /// What may follow a label without being a name ("MÜŞTERİ NÜSHASI", "Sayın Müşterimiz"...).
  static final _notAName = RegExp(
    r'^(?:nusha|kopya|temsilci|hizmet|memnuniyet|no\b|numara|bilgi|kodu|sozlesme|adi\b)',
  );

  static final _email = RegExp(
    r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}',
  );

  // TR + 2 check digits + 22 digits, with spaces; OCR may drop or add a digit, and apps print
  // partly hidden ones ("TR12 3456 **** **** **** 1234").
  static final _iban = RegExp(
    r'(?<![A-Za-z0-9])TR[ \u00a0]?\d{2}(?:[ \u00a0]?[\d*xX•]){16,22}(?![\d*])',
    caseSensitive: false, // OCR sometimes returns "tr33" or "Tr33"
  );

  // "4543 **** **** 1234", "4543 12** **** 1234", "**** **** **** 1234": must hide something.
  static final _cardPartial = RegExp(
    r'(?<![\w*•])(?:[\d*xX•]{4}[ -]?){2,3}[\d*xX•]{4}(?![\w*•])',
  );

  // 13-19 digits, optionally separated by single spaces or dashes.
  static final _cardNumber = RegExp(
    r'(?<![A-Za-z0-9])\d(?:[ -]?\d){12,18}(?![A-Za-z0-9])',
  );

  static final _tckn = RegExp(r'(?<!\d)[1-9]\d{10}(?!\d)');

  // Separators inside a phone number: space, dot, dash (never a line break).
  static const _sep = r'[ \u00a0.\-]?';

  // With a country code. Handled BEFORE the card rule: "0090 532 123 45 67" has 14 digits.
  static final _phoneInternational = RegExp(
    r'(?<!\d)(?:\+90|0090)' +
        _sep +
        r'\(?0?[2-5]\d{2}\)?' +
        _sep +
        r'\d{3}' +
        _sep +
        r'\d{2}' +
        _sep +
        r'\d{2}(?!\d)',
  );

  // 0212 555 12 34 / 0 (532) 123 45 67 / 532 123 45 67.
  static final _phoneLocal = RegExp(
    r'(?<!\d)(?:\(?0' +
        _sep +
        r'\(?[2-5]\d{2}\)?|\(?5\d{2}\)?)' +
        _sep +
        r'\d{3}' +
        _sep +
        r'\d{2}' +
        _sep +
        r'\d{2}(?!\d)',
  );

  // ---- validators --------------------------------------------------------------------------

  static bool _hasHiddenDigits(String match, String before) =>
      RegExp(r'[*xX•]').hasMatch(match);

  static bool _isLuhnCard(String match, String before) {
    final digits = match.replaceAll(RegExp(r'\D'), '');
    return digits.length >= 13 && digits.length <= 19 && _luhn(digits);
  }

  static bool _luhn(String digits) {
    var sum = 0;
    var doubleIt = false;
    for (var i = digits.length - 1; i >= 0; i--) {
      var value = digits.codeUnitAt(i) - 0x30;
      if (doubleIt) {
        value *= 2;
        if (value > 9) value -= 9;
      }
      sum += value;
      doubleIt = !doubleIt;
    }
    return sum % 10 == 0;
  }

  /// The official TCKN rule: 11 digits, first not 0,
  /// d10 = ((d1+d3+d5+d7+d9)*7 - (d2+d4+d6+d8)) mod 10, d11 = (d1+...+d10) mod 10.
  static bool _isValidTckn(String match, String before) {
    if (match.length != 11 || match[0] == '0') return false;
    final d = match.codeUnits.map((unit) => unit - 0x30).toList();
    final odd = d[0] + d[2] + d[4] + d[6] + d[8];
    final even = d[1] + d[3] + d[5] + d[7];
    final tenth = ((odd * 7 - even) % 10 + 10) % 10;
    if (d[9] != tenth) return false;
    final eleventh = d.take(10).fold(0, (sum, digit) => sum + digit) % 10;
    return d[10] == eleventh;
  }

  /// A 10-digit number right after "VKN", "Vergi No", "V.D." is a seller's tax number (public,
  /// and needed to recognise the merchant later), not a phone number.
  static bool _notATaxNumber(String match, String before) {
    final start = before.length > 24
        ? before.substring(before.length - 24)
        : before;
    return !RegExp(r'vkn|vergi|v\.\s?d|\bvd\b|mersis|sicil')
        .hasMatch(foldForMatching(start));
  }
}
