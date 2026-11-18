import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../capture/presentation/shared_media_listener.dart';
import 'add_sheet.dart';
import 'bottom_nav.dart';

/// The frame around the four main tabs: the tab content plus the bottom navigation.
class MainShell extends StatelessWidget {
  const MainShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context) {
    return SharedMediaListener(
      child: Scaffold(
        body: navigationShell,
        bottomNavigationBar: AppBottomNav(
          selectedIndex: navigationShell.currentIndex,
          onTabSelected: (index) => navigationShell.goBranch(
            index,
            // Tapping the tab you are on goes back to its first screen.
            initialLocation: index == navigationShell.currentIndex,
          ),
          onAddPressed: () => showAddSheet(context),
        ),
      ),
    );
  }
}
