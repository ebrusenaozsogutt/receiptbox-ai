import 'package:material_ui/material_ui.dart';

import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/screen_header.dart';

/// Empty for now: products, warranties and return windows arrive in P12.
class ProductsScreen extends StatelessWidget {
  const ProductsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const SafeArea(
      child: Column(
        children: [
          ScreenHeader(title: 'Ürünler'),
          Expanded(
            child: EmptyState(
              icon: Icons.inventory_2_outlined,
              title: 'Ürünlerin burada olacak',
              message: 'Garantisini ve iade süresini takip etmek istediğin ürünleri ekle.',
            ),
          ),
        ],
      ),
    );
  }
}
