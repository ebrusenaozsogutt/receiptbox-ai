import 'package:material_ui/material_ui.dart';

import '../../../core/widgets/placeholder_screen.dart';

/// Placeholders for the three capture actions. Camera, gallery and OCR arrive in P04.
class ScanReceiptScreen extends StatelessWidget {
  const ScanReceiptScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const PlaceholderScreen(
      title: 'Fiş Tara',
      icon: Icons.document_scanner_outlined,
    );
  }
}

class AddFromGalleryScreen extends StatelessWidget {
  const AddFromGalleryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const PlaceholderScreen(
      title: 'Galeriden Ekle',
      icon: Icons.photo_library_outlined,
    );
  }
}

class BankScreenshotScreen extends StatelessWidget {
  const BankScreenshotScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const PlaceholderScreen(
      title: 'Banka Ekran Görüntüsü',
      icon: Icons.account_balance_outlined,
    );
  }
}
