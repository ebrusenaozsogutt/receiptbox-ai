import 'package:material_ui/material_ui.dart';

import '../theme/app_dimens.dart';
import '../theme/app_text_styles.dart';

/// The title row at the top of a main tab, with optional action buttons on the right.
class ScreenHeader extends StatelessWidget {
  const ScreenHeader({super.key, required this.title, this.actions = const []});

  final String title;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.screenH,
        AppSpacing.l,
        AppSpacing.screenH,
        AppSpacing.s,
      ),
      child: SizedBox(
        height: AppSizes.iconButton,
        child: Row(
          children: [
            Expanded(child: Text(title, style: AppTextStyles.titleL)),
            ...actions,
          ],
        ),
      ),
    );
  }
}
