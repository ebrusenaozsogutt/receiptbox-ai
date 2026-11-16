import 'package:material_ui/material_ui.dart';

import '../../../core/widgets/placeholder_screen.dart';

/// "Manuel Harcama": the real form arrives in P07.
class ManualTransactionScreen extends StatelessWidget {
  const ManualTransactionScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const PlaceholderScreen(
      title: 'Manuel Harcama',
      icon: Icons.edit_note_outlined,
    );
  }
}
