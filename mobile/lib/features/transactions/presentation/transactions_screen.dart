import 'package:material_ui/material_ui.dart';

import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/screen_header.dart';

/// Empty for now: the purchase list arrives in P07.
class TransactionsScreen extends StatelessWidget {
  const TransactionsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const SafeArea(
      child: Column(
        children: [
          ScreenHeader(title: 'Harcamalar'),
          Expanded(
            child: EmptyState(
              icon: Icons.receipt_long_outlined,
              title: 'Harcamaların burada listelenecek',
              message: 'Fiş, e-fatura veya banka ekran görüntüsü eklediğinde burada görünür.',
            ),
          ),
        ],
      ),
    );
  }
}
