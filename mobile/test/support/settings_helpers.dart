import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';
import 'package:receiptbox/features/settings/presentation/settings_screen.dart';

/// Settings is longer than the test screen (P13 added BİLDİRİMLER): scroll to [finder] first.
Future<void> scrollSettingsTo(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(
    finder,
    200,
    scrollable: find
        .descendant(
          of: find.byType(SettingsScreen),
          matching: find.byType(Scrollable),
        )
        .first,
  );
  await tester.pumpAndSettle();
}
