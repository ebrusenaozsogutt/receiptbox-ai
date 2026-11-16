import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/storage/settings_store.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import 'auth_scaffold.dart';

/// First-run consent (spec 15.3). Both buttons finish the screen; "Kabul etmiyorum" only turns
/// AI extraction off (manual entry stays possible). The router moves on once it is saved.
class ConsentScreen extends ConsumerWidget {
  const ConsentScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final consent = ref.read(consentSeenProvider.notifier);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              maxWidth: AppSizes.contentMaxWidth,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(
                      AppSpacing.screenH,
                      AppSpacing.xxl,
                      AppSpacing.screenH,
                      AppSpacing.l,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const BrandHeader(),
                        const SizedBox(height: AppSpacing.xxxl),
                        Text(
                          'Verilerin senin kontrolünde',
                          style: AppTextStyles.titleL,
                        ),
                        const SizedBox(height: AppSpacing.xs),
                        Text(
                          'Başlamadan önce verilerinle ne yaptığımızı bilmeni istiyoruz.',
                          style: AppTextStyles.body.copyWith(
                            color: AppColors.textMuted,
                          ),
                        ),
                        const SizedBox(height: AppSpacing.xxl),
                        const _ConsentPoint(
                          icon: Icons.phone_android_outlined,
                          title: 'Fişin telefonunda okunur',
                          body:
                              'Fiş ve banka ekran görüntülerindeki yazılar önce telefonunda '
                              'okunur (OCR). Banka ekran görüntülerinin kendisi telefonundan '
                              'hiçbir zaman çıkmaz.',
                        ),
                        const _ConsentPoint(
                          icon: Icons.visibility_off_outlined,
                          title: 'Kişisel bilgiler gizlenir',
                          body:
                              'IBAN, kart numarası, TC kimlik numarası, telefon, e-posta ve '
                              'bakiye gibi bilgiler, sunucuya gönderilmeden önce telefonunda '
                              'maskelenir.',
                        ),
                        const _ConsentPoint(
                          icon: Icons.auto_awesome_outlined,
                          title: 'Yapay zekâ maskelenmiş metni işler',
                          body:
                              'Maskelenmiş metin; mağaza, tarih ve tutar gibi bilgileri '
                              'çıkarmak için harici bir yapay zekâ hizmeti tarafından '
                              'işlenir. Bu hizmetin ücretsiz sürümleri gönderilen içeriği '
                              'ürünlerini geliştirmek için kullanabilir.',
                        ),
                        const _ConsentPoint(
                          icon: Icons.inventory_2_outlined,
                          title: 'Neler saklanır?',
                          body:
                              'Hesap bilgilerin, onayladığın harcamalar ve ürünler, istersen '
                              'fiş fotoğrafların. Banka ekran görüntüleri asla saklanmaz.',
                        ),
                        const _ConsentPoint(
                          icon: Icons.delete_outline,
                          title: 'Silmek senin elinde',
                          body:
                              'Ayarlar > Hesabı sil ile hesabını ve tüm verilerini kalıcı '
                              'olarak silebilirsin.',
                        ),
                      ],
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(
                    AppSpacing.screenH,
                    AppSpacing.s,
                    AppSpacing.screenH,
                    AppSpacing.l,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      FilledButton(
                        onPressed: () => consent.accept(aiConsent: true),
                        child: const Text('Kabul ediyorum'),
                      ),
                      const SizedBox(height: AppSpacing.s),
                      OutlinedButton(
                        onPressed: () => consent.accept(aiConsent: false),
                        child: const Text('Şimdilik kabul etmiyorum'),
                      ),
                      const SizedBox(height: AppSpacing.s),
                      Text(
                        'Kabul etmezsen yapay zekâ ile okuma kapalı kalır; harcamalarını '
                        'elle girebilirsin.',
                        style: AppTextStyles.bodyS.copyWith(
                          color: AppColors.textMuted,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ConsentPoint extends StatelessWidget {
  const _ConsentPoint({
    required this.icon,
    required this.title,
    required this.body,
  });

  final IconData icon;
  final String title;
  final String body;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.l),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: AppSizes.iconButton,
            height: AppSizes.iconButton,
            decoration: BoxDecoration(
              color: AppColors.primarySoft,
              borderRadius: AppRadius.circular(AppRadius.m),
            ),
            child: Icon(icon, color: AppColors.primary, size: AppSizes.icon),
          ),
          const SizedBox(width: AppSpacing.l),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: AppTextStyles.titleS),
                const SizedBox(height: AppSpacing.xxs),
                Text(
                  body,
                  style: AppTextStyles.bodyS.copyWith(
                    color: AppColors.textMuted,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
