import 'package:material_ui/material_ui.dart';

import '../../../core/widgets/placeholder_screen.dart';

/// "Ürün Ekle": the real form arrives in P12.
class AddProductScreen extends StatelessWidget {
  const AddProductScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const PlaceholderScreen(
      title: 'Ürün Ekle',
      icon: Icons.inventory_2_outlined,
    );
  }
}
