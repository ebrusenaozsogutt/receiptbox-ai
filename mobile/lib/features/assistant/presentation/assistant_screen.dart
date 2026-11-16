import 'package:material_ui/material_ui.dart';

import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/screen_header.dart';

/// Empty for now: the assistant chat arrives in P14.
class AssistantScreen extends StatelessWidget {
  const AssistantScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const SafeArea(
      child: Column(
        children: [
          ScreenHeader(title: 'Asistan'),
          Expanded(
            child: EmptyState(
              icon: Icons.auto_awesome_outlined,
              title: 'Asistan yakında burada',
              message: 'Harcamaların hakkında soru sorabileceksin.',
            ),
          ),
        ],
      ),
    );
  }
}
