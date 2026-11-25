import 'package:intl/intl.dart';

/// "09 Kasım 2026". Needs `initializeDateFormatting('tr_TR')` (done in main.dart).
String formatDateTr(DateTime date) =>
    DateFormat('dd MMMM yyyy', 'tr_TR').format(date);

/// "Aralık 2026" (a month, for the installment schedule).
String formatMonthTr(DateTime date) =>
    DateFormat('MMMM yyyy', 'tr_TR').format(date);

/// "Kas", "Ara", "Şub": a month on a chart axis.
String formatMonthShortTr(DateTime date) =>
    DateFormat('MMM', 'tr_TR').format(date);

/// "Ekim'e", "Kasım'a": the month in the dative ("Ekim'e göre"), with Turkish vowel harmony.
String monthDativeTr(DateTime date) {
  final name = DateFormat('MMMM', 'tr_TR').format(date);
  const back = 'aıou';
  final vowels = name.toLowerCase().split('').where('aeıioöuü'.contains);
  final last = vowels.isEmpty ? 'e' : vowels.last;
  return "$name'${back.contains(last) ? 'a' : 'e'}";
}

/// Upper case the Turkish way: "Ekim" -> "EKİM", "ılık" -> "ILIK" (Dart's toUpperCase gives
/// "EKIM").
String upperTr(String text) =>
    text.replaceAll('i', 'İ').replaceAll('ı', 'I').toUpperCase();
