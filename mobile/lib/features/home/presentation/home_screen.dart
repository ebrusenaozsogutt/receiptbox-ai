import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/theme/app_dimens.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/screen_header.dart';

/// Empty for now: the real Home (spending, needs attention, due this month) arrives in P11.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Column(
        children: [
          ScreenHeader(
            title: 'Ana Sayfa',
            actions: [
              IconButton(
                tooltip: 'Ayarlar',
                constraints: const BoxConstraints.tightFor(
                  width: AppSizes.iconButton,
                  height: AppSizes.iconButton,
                ),
                icon: const Icon(Icons.settings_outlined, size: AppSizes.icon),
                onPressed: () => context.push('/settings'),
              ),
            ],
          ),
          const Expanded(
            child: EmptyState(
              icon: Icons.home_outlined,
              title: 'Henüz harcama yok',
              message: 'İlk fişini eklemek için aşağıdaki + düğmesine dokun.',
            ),
          ),
        ],
      ),
    );
  }
}
