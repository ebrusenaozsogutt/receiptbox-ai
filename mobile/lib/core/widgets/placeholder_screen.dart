import 'package:material_ui/material_ui.dart';

import 'empty_state.dart';

/// A pushed screen (with a back arrow) for features that are built in later phases.
class PlaceholderScreen extends StatelessWidget {
  const PlaceholderScreen({super.key, required this.title, required this.icon});

  final String title;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: EmptyState(
        icon: icon,
        title: 'Bu özellik yakında',
        message: 'Bu ekran sonraki aşamalarda eklenecek.',
      ),
    );
  }
}
