import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';

/// One action of the (+) sheet and the placeholder screen it opens.
class AddAction {
  const AddAction({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.route,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final String route;
}

/// The five actions of spec 17, in this order.
const addActions = [
  AddAction(
    title: 'Fiş Tara',
    subtitle: 'Kamerayla fişini çek',
    icon: Icons.document_scanner_outlined,
    route: '/capture/scan',
  ),
  AddAction(
    title: 'Galeriden Ekle',
    subtitle: 'Galerindeki bir fiş veya fatura',
    icon: Icons.photo_library_outlined,
    route: '/capture/gallery',
  ),
  AddAction(
    title: 'Banka Ekran Görüntüsü',
    subtitle: 'Banka uygulamasındaki harcama listesi',
    icon: Icons.account_balance_outlined,
    route: '/capture/bank',
  ),
  AddAction(
    title: 'Manuel Harcama',
    subtitle: 'Fişi olmayan bir harcamayı elle gir',
    icon: Icons.edit_note_outlined,
    route: '/transactions/new',
  ),
  AddAction(
    title: 'Ürün Ekle',
    subtitle: 'Garantisini takip etmek istediğin ürün',
    icon: Icons.inventory_2_outlined,
    route: '/products/new',
  ),
];

/// Opens the (+) bottom sheet. Choosing an action closes it and opens that screen.
Future<void> showAddSheet(BuildContext context) {
  return showModalBottomSheet<void>(
    context: context,
    useRootNavigator: true,
    // Scrollable and allowed to grow: five two-line rows do not fit in the default sheet
    // height (9/16 of the screen) on short screens or with a large system font.
    isScrollControlled: true,
    builder: (sheetContext) => SafeArea(
      child: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.screenH,
            AppSpacing.none,
            AppSpacing.screenH,
            AppSpacing.l,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Ne eklemek istersin?', style: AppTextStyles.titleM),
              const SizedBox(height: AppSpacing.s),
              for (final action in addActions)
                ListTile(
                  key: Key('add_action_${action.route}'),
                  contentPadding: EdgeInsets.zero,
                  leading: Container(
                    width: AppSizes.iconButton,
                    height: AppSizes.iconButton,
                    decoration: BoxDecoration(
                      color: AppColors.primarySoft,
                      borderRadius: AppRadius.circular(AppRadius.m),
                    ),
                    child: Icon(
                      action.icon,
                      color: AppColors.primary,
                      size: AppSizes.icon,
                    ),
                  ),
                  title: Text(action.title),
                  subtitle: Text(action.subtitle),
                  onTap: () {
                    Navigator.of(sheetContext).pop();
                    context.push(action.route);
                  },
                ),
            ],
          ),
        ),
      ),
    ),
  );
}
