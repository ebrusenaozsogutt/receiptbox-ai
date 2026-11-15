import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../data/health_repository.dart';

/// P00 placeholder screen: proves the app can reach the backend.
class HealthScreen extends ConsumerWidget {
  const HealthScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final health = ref.watch(healthStatusProvider);

    final (String label, IconData icon, Color color) = health.when(
      loading: () => ('Sunucu: kontrol ediliyor…', Icons.sync, Colors.grey),
      error: (_, _) => ('Sunucu: bağlantı yok', Icons.cloud_off, Colors.red),
      data: (status) => status.isHealthy
          ? ('Sunucu: bağlı', Icons.cloud_done, Colors.green)
          : ('Sunucu: veritabanı hatası', Icons.warning_amber, Colors.orange),
    );

    return Scaffold(
      appBar: AppBar(title: const Text('ReceiptBox AI')),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 64, color: color),
            const SizedBox(height: 16),
            Text(label, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: () => ref.invalidate(healthStatusProvider),
              child: const Text('Tekrar dene'),
            ),
          ],
        ),
      ),
    );
  }
}
