import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../analytics/data/analytics_providers.dart';
import '../../capture/presentation/shared_media_listener.dart';
import '../../matching/presentation/merge_feedback.dart';
import 'add_sheet.dart';
import 'bottom_nav.dart';

/// The frame around the four main tabs: the tab content plus the bottom navigation.
class MainShell extends ConsumerWidget {
  const MainShell({super.key, required this.navigationShell});

  /// The Home tab: its numbers are loaded again every time it is opened (a purchase saved on
  /// another screen changes them).
  static const int homeTab = 0;

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return SharedMediaListener(
      child: Scaffold(
        body: navigationShell,
        bottomNavigationBar: AppBottomNav(
          selectedIndex: navigationShell.currentIndex,
          onTabSelected: (index) {
            // Another tab: the "Geri al" of the screen you leave does not follow you.
            if (index != navigationShell.currentIndex) dismissMergedSnackBar();
            if (index == homeTab) ref.invalidate(homeDataProvider);
            navigationShell.goBranch(
              index,
              // Tapping the tab you are on goes back to its first screen.
              initialLocation: index == navigationShell.currentIndex,
            );
          },
          onAddPressed: () => showAddSheet(context),
        ),
      ),
    );
  }
}
