import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../data/health_repository.dart';

/// "Sunucu: bağlı" / "Sunucu: bağlantı yok": a small diagnostic row (shown in Settings).
class ServerStatusTile extends ConsumerWidget {
  const ServerStatusTile({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final health = ref.watch(healthStatusProvider);

    final (String label, IconData icon, Color color) = health.when(
      loading: () =>
          ('Sunucu: kontrol ediliyor…', Icons.sync, AppColors.textSubtle),
      error: (_, _) =>
          ('Sunucu: bağlantı yok', Icons.cloud_off, AppColors.danger),
      data: (status) => status.isHealthy
          ? ('Sunucu: bağlı', Icons.cloud_done, AppColors.success)
          : (
              'Sunucu: veritabanı hatası',
              Icons.warning_amber,
              AppColors.warning,
            ),
    );

    return ListTile(
      leading: Icon(icon, color: color, size: AppSizes.icon),
      title: Text(label),
      trailing: TextButton(
        onPressed: () => ref.invalidate(healthStatusProvider),
        child: const Text('Tekrar dene'),
      ),
    );
  }
}
