import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/storage/settings_store.dart';
import '../../../core/theme/app_button_styles.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../health/presentation/server_status_tile.dart';

/// Settings (opened from the Home app bar): privacy toggle, server status, sign out and
/// delete account. Leaving the signed-in state is handled by the router.
class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  bool _busy = false;

  Future<void> _logout() async {
    setState(() => _busy = true);
    await ref.read(authProvider.notifier).logout();
    // The router now shows Login; this screen is gone.
  }

  Future<void> _setAiConsent(bool value) async {
    try {
      await ref.read(authProvider.notifier).setAiConsent(value);
    } on ApiError {
      if (!mounted) return;
      // The choice is saved on this device and will be sent again; say so.
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Ayar bu cihaza kaydedildi ama sunucuya iletilemedi. '
            'Bağlantı gelince yeniden denenecek.',
          ),
        ),
      );
    }
  }

  Future<void> _confirmAndDelete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Hesabını sil?'),
        content: const Text(
          'Tüm fişlerin, harcamaların ve ürünlerin kalıcı olarak silinir. '
          'Bu işlem geri alınamaz.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('İptal'),
          ),
          FilledButton(
            style: AppButtonStyles.danger(),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Hesabı sil'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _busy = true);
    try {
      // On success the router shows Register (this device no longer has an account).
      await ref.read(authProvider.notifier).deleteAccount();
    } on ApiError catch (error) {
      if (!mounted) return;
      setState(() => _busy = false);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(error.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final email = ref.watch(authProvider).user?.email;
    final keepImages = ref.watch(keepReceiptImagesProvider);
    final aiConsent = ref.watch(aiConsentProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Ayarlar')),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.screenH),
        children: [
          const _SectionLabel('HESAP'),
          Card(
            child: ListTile(
              leading: const Icon(Icons.person_outline),
              title: const Text('E-posta'),
              subtitle: Text(email ?? '—'),
            ),
          ),
          const SizedBox(height: AppSpacing.xxl),
          const _SectionLabel('GİZLİLİK'),
          Card(
            child: SwitchListTile(
              key: const Key('ai_consent_switch'),
              contentPadding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.l,
              ),
              title: const Text('Yapay zekâ ile fiş okuma'),
              subtitle: const Text(
                'Açıkken, fişten okunan ve kişisel bilgileri silinmiş metin '
                'harici bir yapay zekâ servisine gönderilir. Kapalıyken yalnızca '
                'elle giriş yapabilirsin.',
              ),
              value: aiConsent,
              onChanged: _setAiConsent,
            ),
          ),
          const SizedBox(height: AppSpacing.s),
          Card(
            child: SwitchListTile(
              key: const Key('keep_images_switch'),
              contentPadding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.l,
              ),
              title: const Text('Fiş görsellerini sakla'),
              subtitle: const Text(
                'Fiş fotoğrafları garanti kanıtı olarak saklanır. '
                'Banka ekran görüntüleri hiçbir zaman saklanmaz.',
              ),
              value: keepImages,
              onChanged: (value) =>
                  ref.read(keepReceiptImagesProvider.notifier).set(value),
            ),
          ),
          const SizedBox(height: AppSpacing.xxl),
          const _SectionLabel('BAĞLANTI'),
          const Card(child: ServerStatusTile()),
          const SizedBox(height: AppSpacing.xxxl),
          OutlinedButton(
            onPressed: _busy ? null : _logout,
            child: const Text('Çıkış yap'),
          ),
          const SizedBox(height: AppSpacing.s),
          TextButton(
            style: AppButtonStyles.dangerText(),
            onPressed: _busy ? null : _confirmAndDelete,
            child: const Text('Hesabı sil'),
          ),
        ],
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.s),
      child: Text(
        text, // already upper case: Dart's toUpperCase() would turn 'i' into 'I', not 'İ'
        style: AppTextStyles.overline.copyWith(color: AppColors.textMuted),
      ),
    );
  }
}
