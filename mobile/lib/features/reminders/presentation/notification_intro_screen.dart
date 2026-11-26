import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../data/notification_gateway.dart';
import '../data/reminder_prefs.dart';
import '../data/reminder_sync.dart';

/// Shown once, before the Android 13+ permission dialog: why ReceiptBox wants to send
/// notifications. "Şimdi değil" never asks again from here (Settings can).
class NotificationIntroScreen extends ConsumerStatefulWidget {
  const NotificationIntroScreen({super.key});

  @override
  ConsumerState<NotificationIntroScreen> createState() =>
      _NotificationIntroScreenState();
}

class _NotificationIntroScreenState
    extends ConsumerState<NotificationIntroScreen> {
  var _busy = false;

  Future<void> _finish({required bool ask}) async {
    setState(() => _busy = true);
    final router = GoRouter.of(context);
    await ref.read(reminderPrefsProvider).setIntroSeen();
    if (ask) {
      await ref.read(notificationGatewayProvider).requestPermission();
      await ref.read(reminderSyncProvider).sync();
    }
    if (router.canPop()) {
      router.pop();
    } else {
      router.go('/home');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.screenH),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Spacer(),
              const Icon(
                Icons.notifications_active_outlined,
                size: AppSizes.iconXl,
                color: AppColors.primary,
              ),
              const SizedBox(height: AppSpacing.xxl),
              Text(
                'Son günleri kaçırma',
                textAlign: TextAlign.center,
                style: AppTextStyles.titleL,
              ),
              const SizedBox(height: AppSpacing.m),
              Text(
                'ReceiptBox sana yalnızca şu durumlarda bildirim gönderir: garantinin '
                'bitmesine 30 ve 7 gün kala, iade süresinin bitmesine 3 gün ve 1 gün kala, '
                'son taksit ayında ve bir bütçenin %80 ya da %100’üne ulaştığında.',
                textAlign: TextAlign.center,
                style: AppTextStyles.body.copyWith(color: AppColors.textMuted),
              ),
              const SizedBox(height: AppSpacing.m),
              Text(
                'Bildirimler telefonunda kurulur; hangilerini alacağını Ayarlar’dan '
                'seçebilirsin.',
                textAlign: TextAlign.center,
                style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
              ),
              const Spacer(),
              FilledButton(
                key: const Key('notifications_allow'),
                onPressed: _busy ? null : () => _finish(ask: true),
                child: const Text('Bildirimlere izin ver'),
              ),
              const SizedBox(height: AppSpacing.s),
              TextButton(
                key: const Key('notifications_later'),
                onPressed: _busy ? null : () => _finish(ask: false),
                child: const Text('Şimdi değil'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
