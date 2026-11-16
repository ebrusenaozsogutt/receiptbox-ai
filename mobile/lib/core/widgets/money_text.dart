import 'package:material_ui/material_ui.dart';

import '../theme/app_text_styles.dart';
import '../utils/money_format.dart';

/// An amount in minor units (kuruş) shown as "1.349,90 TL".
class MoneyText extends StatelessWidget {
  const MoneyText(this.minor, {super.key, this.style, this.textAlign});

  final int minor;
  final TextStyle? style;
  final TextAlign? textAlign;

  @override
  Widget build(BuildContext context) {
    return Text(
      formatMoneyTl(minor),
      style: style ?? AppTextStyles.body,
      textAlign: textAlign,
    );
  }
}
