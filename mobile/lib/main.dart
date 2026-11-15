import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:intl/intl.dart';

import 'app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Turkish dates and numbers, e.g. "09 Kasım 2026" and "1.349,90".
  Intl.defaultLocale = 'tr_TR';
  await initializeDateFormatting('tr_TR');
  runApp(const ProviderScope(child: ReceiptBoxApp()));
}
