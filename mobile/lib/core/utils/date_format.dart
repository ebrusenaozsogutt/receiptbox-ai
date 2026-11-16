import 'package:intl/intl.dart';

/// "09 Kasım 2026". Needs `initializeDateFormatting('tr_TR')` (done in main.dart).
String formatDateTr(DateTime date) =>
    DateFormat('dd MMMM yyyy', 'tr_TR').format(date);
