import 'package:flutter/painting.dart';

import 'app_colors.dart';

/// Design tokens: spacing, corner radii, component sizes, shadows.

/// Spacing scale (logical pixels).
class AppSpacing {
  const AppSpacing._();

  static const double none = 0;
  static const double xxs = 4;
  static const double xs = 6;
  static const double s = 8;
  static const double m = 12;
  static const double inputGap = 14; // between form fields, inside input boxes
  static const double l = 16;
  static const double xl = 20; // horizontal screen margin
  static const double xxl = 24;
  static const double xxxl = 32;
  static const double huge = 48;

  /// Horizontal margin of every screen.
  static const double screenH = xl;
}

/// Corner radii: 8 / 12 / 16 / 24 from the design, plus two component-specific ones.
class AppRadius {
  const AppRadius._();

  static const double xs = 4; // check boxes
  static const double s = 8;
  static const double m = 12; // buttons, inputs
  static const double l = 16; // cards
  static const double xl = 24; // bottom sheets
  static const double segment =
      9; // selected segment inside a segmented control
  static const double navAddButton = 18; // the raised (+) button

  static BorderRadius circular(double radius) => BorderRadius.circular(radius);
  static const BorderRadius card = BorderRadius.all(Radius.circular(l));
  static const BorderRadius control = BorderRadius.all(Radius.circular(m));
  static const BorderRadius sheetTop = BorderRadius.vertical(
    top: Radius.circular(xl),
  );
}

/// Sizes of components and icons.
class AppSizes {
  const AppSizes._();

  static const double minTapTarget =
      48; // accessibility minimum (WCAG, Material)
  static const double buttonHeight = 48;
  static const double inputHeight = 48;
  static const double borderWidth = 1;
  static const double borderWidthStrong =
      1.5; // secondary button, focused input

  static const double iconS = 18; // icons inside inputs
  static const double icon = 24;
  static const double iconAdd = 26; // the plus inside the (+) button
  static const double iconXl = 56; // icon on empty states / splash
  static const double iconButton = 44; // round icon buttons in app bars

  static const double navHeight = 76;
  static const double navAddButton = 56;
  static const double navTabMinWidth = 48;
  static const double navTabGap = 4; // icon to label
  static const double navHorizontalPadding = 20;

  /// Largest system text scale the bottom bar follows. Beyond it the labels would no longer
  /// fit in five slots on a narrow phone.
  static const double navMaxTextScale = 1.2;

  static const double progressThickness = 3;
  static const double progressSize = 28;
  static const double contentMaxWidth = 480; // keeps forms readable on tablets
  static const double dragHandleWidth = 40;
  static const double dragHandleHeight = 4;
  static const double emptyStateMaxWidth = 320;
  static const double switchTrackHeight = 28;
}

class AppShadows {
  const AppShadows._();

  /// Shadow of the raised (+) button: 0 6 14, rgba(13, 94, 87, 0.30).
  static const List<BoxShadow> navAddButton = [
    BoxShadow(
      color: AppColors.primaryShadow,
      offset: Offset(0, 6),
      blurRadius: 14,
    ),
  ];

  /// Selected segment of a segmented control: 0 1 3, rgba(0, 0, 0, 0.08).
  static const List<BoxShadow> segment = [
    BoxShadow(
      color: AppColors.subtleShadow,
      offset: Offset(0, 1),
      blurRadius: 3,
    ),
  ];
}
