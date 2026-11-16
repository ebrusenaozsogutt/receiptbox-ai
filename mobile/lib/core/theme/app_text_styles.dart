import 'package:flutter/painting.dart';

import 'app_colors.dart';

/// Design tokens: typography. Plus Jakarta Sans (Turkish glyphs included), type scale from
/// docs/design/DESIGN_TRACK.md. Sizes are "size / line height" in logical pixels.
class AppTextStyles {
  const AppTextStyles._();

  static const String fontFamily = 'PlusJakartaSans';

  static TextStyle _style(
    double size,
    double lineHeight,
    int weight, {
    double letterSpacingPercent = 0,
  }) {
    return TextStyle(
      fontFamily: fontFamily,
      fontSize: size,
      height: lineHeight / size,
      fontWeight: FontWeight.values[(weight ~/ 100) - 1],
      // One variable font file: the real weight is set on its `wght` axis.
      fontVariations: [FontVariation('wght', weight.toDouble())],
      letterSpacing: size * letterSpacingPercent / 100,
      color: AppColors.text,
    );
  }

  /// 32/40 ExtraBold: big numbers such as the monthly total.
  static final TextStyle display = _style(32, 40, 800);

  /// 22/28 Bold: screen titles.
  static final TextStyle titleL = _style(22, 28, 700);

  /// 18/24 Bold.
  static final TextStyle titleM = _style(18, 24, 700);

  /// 16/22 SemiBold.
  static final TextStyle titleS = _style(16, 22, 600);

  /// 15/22 Regular: normal text.
  static final TextStyle body = _style(15, 22, 400);

  /// 15/22 SemiBold: button labels, emphasised text.
  static final TextStyle bodyStrong = _style(15, 22, 600);

  /// 13/18 Regular: secondary text.
  static final TextStyle bodyS = _style(13, 18, 400);

  /// 13/16 SemiBold: field labels.
  static final TextStyle label = _style(13, 16, 600);

  /// 12/16 Medium: tab labels, captions.
  static final TextStyle caption = _style(12, 16, 500);

  /// 11/14 Bold, +8% letter spacing: small upper-case headings.
  static final TextStyle overline = _style(
    11,
    14,
    700,
    letterSpacingPercent: 8,
  );
}
