import 'package:material_ui/material_ui.dart';

import '../theme/app_text_styles.dart';
import '../utils/date_format.dart';

/// A date shown as "09 Kasım 2026".
class DateText extends StatelessWidget {
  const DateText(this.date, {super.key, this.style});

  final DateTime date;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    return Text(formatDateTr(date), style: style ?? AppTextStyles.body);
  }
}
