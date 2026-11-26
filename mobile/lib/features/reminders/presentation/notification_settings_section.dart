import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../products/data/products_api.dart';
import '../data/notification_gateway.dart';
import '../data/reminder_prefs.dart';
import '../data/reminder_sync.dart';
import '../domain/notification_plan.dart';
import '../domain/reminder_models.dart';

/// Permission and exact-alarm state as the phone reports it (re-read when Settings opens).
final notificationStatusProvider =
    FutureProvider.autoDispose<({bool enabled, bool exact})>((ref) async {
      final gateway = ref.watch(notificationGatewayProvider);
      try {
        return (
          enabled: await gateway.notificationsEnabled(),
          exact: await gateway.canScheduleExact(),
        );
      } on Object {
        return (enabled: false, exact: false);
      }
    });

/// Settings → BİLDİRİMLER: the permission, one switch per kind, exact alarms, and in debug
/// builds a "2 dakika sonra bildir" button per kind.
class NotificationSettingsSection extends ConsumerWidget {
  const NotificationSettingsSection({super.key});

  Future<void> _askPermission(WidgetRef ref) async {
    await ref.read(notificationGatewayProvider).requestPermission();
    ref.invalidate(notificationStatusProvider);
    await ref.read(reminderSyncProvider).sync();
  }

  Future<void> _askExact(WidgetRef ref) async {
    await ref.read(notificationGatewayProvider).requestExactAlarms();
    ref.invalidate(notificationStatusProvider);
    await ref.read(reminderSyncProvider).sync();
  }

  Future<void> _toggle(WidgetRef ref, ReminderKind kind, bool value) async {
    await ref.read(notificationKindsProvider.notifier).set(kind, value);
    await ref.read(reminderSyncProvider).sync();
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final kinds = ref.watch(notificationKindsProvider);
    final status = ref.watch(notificationStatusProvider).value;
    final enabled = status?.enabled ?? true;
    final exact = status?.exact ?? false;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (!enabled)
          Card(
            child: ListTile(
              key: const Key('notifications_permission_tile'),
              leading: const Icon(
                Icons.notifications_off_outlined,
                color: AppColors.warning,
              ),
              title: const Text('Bildirimler kapalı'),
              subtitle: const Text(
                'Hatırlatmaları alamazsın. İzin ver; pencere açılmazsa telefonun '
                'Ayarlar > Uygulamalar > ReceiptBox AI > Bildirimler bölümünden aç.',
              ),
              trailing: TextButton(
                key: const Key('notifications_permission_button'),
                onPressed: () => _askPermission(ref),
                child: const Text('İzin ver'),
              ),
            ),
          ),
        if (!enabled) const SizedBox(height: AppSpacing.s),
        Card(
          child: Column(
            children: [
              for (final kind in ReminderKind.values)
                SwitchListTile(
                  key: Key('notifications_${kind.name}'),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.l,
                  ),
                  title: Text(kind.label),
                  subtitle: Text(_describe(kind)),
                  value: kinds.contains(kind),
                  onChanged: (value) => _toggle(ref, kind, value),
                ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.s),
        Card(
          child: ListTile(
            key: const Key('notifications_exact_tile'),
            leading: const Icon(Icons.alarm_outlined),
            title: const Text('Tam zamanlı bildirimler'),
            subtitle: Text(
              exact
                  ? 'Açık: hatırlatmalar tam saatinde (10:00) gelir.'
                  : 'Kapalı: hatırlatmalar birkaç dakika gecikebilir.',
            ),
            trailing: exact
                ? null
                : TextButton(
                    key: const Key('notifications_exact_button'),
                    onPressed: () => _askExact(ref),
                    child: const Text('Aç'),
                  ),
          ),
        ),
        if (kDebugMode) ...[
          const SizedBox(height: AppSpacing.s),
          const _DebugButtons(),
        ],
      ],
    );
  }

  static String _describe(ReminderKind kind) => switch (kind) {
    ReminderKind.warranty => 'Garantinin bitmesine 30 ve 7 gün kala',
    ReminderKind.returnWindow => 'İade süresinin bitmesine 3 gün ve 1 gün kala',
    ReminderKind.installment => 'Son taksitin ödeneceği ayın 1’inde',
    ReminderKind.budget => 'Bir bütçe %80’e ve %100’e ulaştığında',
  };
}

/// Debug builds only: schedule a sample notification of each kind 2 minutes ahead, to check
/// delivery and the deep link by hand. Local only, under ids 1–4 (a sync never cancels them).
class _DebugButtons extends ConsumerWidget {
  const _DebugButtons();

  Future<void> _fire(
    BuildContext context,
    WidgetRef ref,
    ReminderKind kind,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    final gateway = ref.read(notificationGatewayProvider);
    String route;
    String body;
    switch (kind) {
      case ReminderKind.warranty:
      case ReminderKind.returnWindow:
        final products = await ref.read(productsApiProvider).list();
        if (products.isEmpty) {
          messenger.showSnackBar(
            const SnackBar(content: Text('Önce bir ürün ekle.')),
          );
          return;
        }
        final product = products.first;
        route = '/products/${product.id}';
        body = kind == ReminderKind.warranty
            ? '(Deneme) ${product.name}: garanti süresinin bitmesine 30 gün kaldı.'
            : '(Deneme) ${product.name}: iade süresi yarın bitiyor.';
      case ReminderKind.installment:
        route = '/installments';
        body = '(Deneme) MediaMarkt taksitlerinin sonuncusu bu ay.';
      case ReminderKind.budget:
        route = '/budgets';
        body = "(Deneme) Market bütçenin %80'ine ulaştın.";
    }
    await gateway.schedule(
      id: debugNotificationIdFor(kind),
      title: '${kind.label} (deneme)',
      body: body,
      at: DateTime.now().add(const Duration(minutes: 2)),
      payload: route,
      exact: await gateway.canScheduleExact(),
    );
    messenger.showSnackBar(
      SnackBar(
        content: Text('${kind.label} bildirimi 2 dakika sonra gelecek.'),
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      color: AppColors.surfaceAlt,
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.l),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Geliştirici: 2 dakika sonra bildir',
              style: AppTextStyles.label,
            ),
            const SizedBox(height: AppSpacing.s),
            Wrap(
              spacing: AppSpacing.s,
              runSpacing: AppSpacing.s,
              children: [
                for (final kind in ReminderKind.values)
                  OutlinedButton(
                    key: Key('debug_notify_${kind.name}'),
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size(0, AppSizes.buttonHeight),
                    ),
                    onPressed: () => _fire(context, ref, kind),
                    child: Text(kind.label),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
