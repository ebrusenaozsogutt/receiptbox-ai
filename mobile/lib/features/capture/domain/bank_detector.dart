import '../../../core/privacy/pii_masker.dart';
import 'bank_models.dart';

/// Guesses the bank from the MASKED text of a screenshot with a small keyword table (spec 5.5).
/// Only the three supported banks have keywords; a screenshot of any other bank gives null, which
/// the server reads with the general prompt. The user can change the guess on the review screen.
class BankDetector {
  const BankDetector();

  // Folded text (no Turkish letters, lower case). OCR slips such as "KuUEYTTÜRK" are covered.
  static final _keywords = <BankKey, List<RegExp>>{
    BankKey.garanti: [
      RegExp(r'garanti'),
      RegExp(r'\bbbva\b'),
      RegExp(r'\bbonus\b'),
      RegExp(r'hesap ve kart'),
      RegExp(r'son donem ici hareketleri'),
    ],
    BankKey.kuveyt: [
      RegExp(r'ku[uvw]e[vyuw]{1,2}t\s?turk'),
      RegExp(r'kuveyt'),
      RegExp(r'\bdoviz/yatir'),
      RegExp(r'toplam altin puan'),
      RegExp(r'donem ici harcamalar'),
    ],
    BankKey.akbank: [
      RegExp(r'akbank'),
      RegExp(r'a[ix]{1,2}ess'),
      RegExp(r'chip[ -]?para'),
      RegExp(r'dijital slip'),
      RegExp(r'dijiortak'),
    ],
  };

  /// The bank whose keywords appear most often; null when none appears or two banks tie.
  BankKey? detect(String maskedText) {
    final folded = PiiMasker.foldForMatching(maskedText);
    BankKey? best;
    var bestScore = 0;
    var tie = false;
    for (final entry in _keywords.entries) {
      final score = entry.value.where((k) => k.hasMatch(folded)).length;
      if (score > bestScore) {
        best = entry.key;
        bestScore = score;
        tie = false;
      } else if (score == bestScore && score > 0) {
        tie = true;
      }
    }
    return tie ? null : best;
  }
}
