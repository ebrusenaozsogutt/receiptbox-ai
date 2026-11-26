/// Turkish case endings for names inside notification texts ("AirPods'un", "Trendyol'dan").
///
/// Vowel harmony uses the last vowel as it is READ: an acronym such as "TV" or "LG" is read by
/// its letter names ("te-ve" → "TV'nin"), a name ending in a digit by the number word
/// ("Galaxy S24" → "yirmi dört" → "S24'ün"). Foreign words are taken as written ("Kettle'nin"),
/// not as pronounced: good enough for a reminder and never wrong about the numbers.
library;

const _frontVowels = 'eiöü';
const _vowels = 'aeıioöuü';
const _hardConsonants = 'fstkçşhp';

/// How the last letter of an acronym is read: "be, ce, … ka, … ve".
const _letterNames = {
  'a': 'a',
  'b': 'be',
  'c': 'ce',
  'ç': 'çe',
  'd': 'de',
  'e': 'e',
  'f': 'fe',
  'g': 'ge',
  'ğ': 'yumuşak ge',
  'h': 'he',
  'ı': 'ı',
  'i': 'i',
  'j': 'je',
  'k': 'ka',
  'l': 'le',
  'm': 'me',
  'n': 'ne',
  'o': 'o',
  'ö': 'ö',
  'p': 'pe',
  'q': 'kü',
  'r': 're',
  's': 'se',
  'ş': 'şe',
  't': 'te',
  'u': 'u',
  'ü': 'ü',
  'v': 've',
  'w': 'dabılyu',
  'x': 'iks',
  'y': 'ye',
  'z': 'ze',
};

/// How a number ending is read (the last digit, or "on/yirmi/…" for 10, 20, …).
const _digitWords = {
  '0': 'sıfır',
  '1': 'bir',
  '2': 'iki',
  '3': 'üç',
  '4': 'dört',
  '5': 'beş',
  '6': 'altı',
  '7': 'yedi',
  '8': 'sekiz',
  '9': 'dokuz',
};
const _tensWords = {
  '1': 'on',
  '2': 'yirmi',
  '3': 'otuz',
  '4': 'kırk',
  '5': 'elli',
  '6': 'altmış',
  '7': 'yetmiş',
  '8': 'seksen',
  '9': 'doksan',
};

String _lowerTr(String text) =>
    text.replaceAll('I', 'ı').replaceAll('İ', 'i').toLowerCase();

/// The name without trailing quotes, dots and spaces ('Samsung 55" TV' stays, 'TV"' → 'TV').
String _trimmed(String name) =>
    name.trimRight().replaceAll(RegExp(r'''["'’.,!?)\]]+$'''), '').trimRight();

/// The ending as it sounds, in lower case.
String _spoken(String name) {
  final trimmed = _trimmed(name);
  final word = trimmed.split(RegExp(r'\s+')).last;
  final digits = RegExp(r'(\d+)$').firstMatch(word);
  if (digits != null) {
    final number = digits.group(1)!;
    final last = number[number.length - 1];
    if (last == '0' && number.length >= 2) {
      final tens = number[number.length - 2];
      if (tens != '0') return _tensWords[tens]!;
      return 'yüz'; // 100, 200 … (good enough for model numbers)
    }
    return _digitWords[last]!;
  }
  final lower = _lowerTr(word);
  final isAcronym =
      word.length <= 4 &&
      word == word.toUpperCase() &&
      !_vowels.contains(lower[lower.length - 1]);
  if (isAcronym) {
    return _letterNames[lower[lower.length - 1]] ?? lower;
  }
  return lower;
}

String? _lastVowel(String spoken) {
  for (var i = spoken.length - 1; i >= 0; i--) {
    if (_vowels.contains(spoken[i])) return spoken[i];
  }
  return null;
}

bool _endsWithVowel(String spoken) =>
    spoken.isNotEmpty && _vowels.contains(spoken[spoken.length - 1]);

/// ı / i / u / ü after the last vowel (four-way harmony).
String _fourWay(String? vowel) {
  switch (vowel) {
    case 'e':
    case 'i':
      return 'i';
    case 'o':
    case 'u':
      return 'u';
    case 'ö':
    case 'ü':
      return 'ü';
    default:
      return 'ı';
  }
}

/// a / e after the last vowel (two-way harmony).
String _twoWay(String? vowel) =>
    vowel != null && _frontVowels.contains(vowel) ? 'e' : 'a';

/// A name with a capital letter anywhere (brands, shops: "AirPods", "iPhone") or ending in a
/// number takes an apostrophe; a lower-case common noun does not ("ayakkabının").
bool _isProperName(String name) {
  final trimmed = name.trim();
  if (trimmed.isEmpty) return false;
  return trimmed != _lowerTr(trimmed) || RegExp(r'\d$').hasMatch(trimmed);
}

/// Genitive: "AirPods" → "AirPods'un", "TV" → "TV'nin", "ayakkabı" → "ayakkabının".
String genitive(String name) {
  final base = _trimmed(name);
  final spoken = _spoken(name);
  final vowel = _fourWay(_lastVowel(spoken));
  final ending = _endsWithVowel(spoken) ? 'n${vowel}n' : '${vowel}n';
  return _isProperName(base) ? "$base'$ending" : '$base$ending';
}

/// Ablative: "Trendyol" → "Trendyol'dan", "MediaMarkt" → "MediaMarkt'tan", "Teknosa" →
/// "Teknosa'dan".
String ablative(String name) {
  final base = _trimmed(name);
  final spoken = _spoken(name);
  final vowel = _twoWay(_lastVowel(spoken));
  final last = spoken.isEmpty ? '' : spoken[spoken.length - 1];
  final consonant = _hardConsonants.contains(last) ? 't' : 'd';
  final ending = '$consonant${vowel}n';
  return _isProperName(base) ? "$base'$ending" : '$base$ending';
}
