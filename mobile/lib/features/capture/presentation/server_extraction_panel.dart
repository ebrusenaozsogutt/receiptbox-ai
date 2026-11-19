import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/storage/settings_store.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/widgets/message_banner.dart';
import '../data/capture_providers.dart';
import '../data/extraction_api.dart';
import '../domain/capture_payload.dart';
import '../domain/extraction_result.dart';

/// DEBUG BUILDS ONLY. A button that sends the (already masked) capture to the backend and
/// shows what came back, so that the owner can check the QR path, the extraction, the
/// confidence and the merchant / category suggestions on the emulator. It is not the review
/// screen (P07) and does not exist in release builds.
class ServerExtractionPanel extends ConsumerStatefulWidget {
  const ServerExtractionPanel({super.key, required this.payload});

  final CapturePayload payload;

  @override
  ConsumerState<ServerExtractionPanel> createState() =>
      _ServerExtractionPanelState();
}

class _ServerExtractionPanelState extends ConsumerState<ServerExtractionPanel> {
  bool _sending = false;
  String? _error;
  ExtractionResult? _result;

  Future<void> _send() async {
    setState(() {
      _sending = true;
      _error = null;
      _result = null;
    });
    try {
      final result = await ref
          .read(extractionApiProvider)
          .extract(widget.payload, aiConsent: ref.read(aiConsentProvider));
      if (!mounted) return;
      setState(() => _result = result);
    } on AiConsentOffException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } on ExtractionNotAvailableException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } on ApiError catch (error) {
      if (mounted) setState(() => _error = _describe(error));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  String _describe(ApiError error) {
    switch (error.code) {
      case 'AI_CONSENT_REQUIRED':
        return const AiConsentOffException().message;
      case 'EXTRACTION_FAILED':
        return 'Fiş şu an okunamadı (yapay zekâ servisi yanıt vermedi). '
            'Tekrar dene ya da elle ekle.';
      case 'EXTRACTION_REJECTED':
        return 'Fiş güvenilir okunamadı (tutar mantıksız). Elle ekleyebilirsin.';
      case 'QR_INVALID':
        return 'QR kodu okunabilir bir e-Arşiv / e-Fatura QR\'ı değil.';
      case 'TEXT_TOO_LARGE':
        return 'Metin çok uzun (en fazla 20 KB).';
      default:
        return error.message;
    }
  }

  @override
  Widget build(BuildContext context) {
    final result = _result;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Sunucu (yalnızca debug)', style: AppTextStyles.label),
        const SizedBox(height: AppSpacing.xs),
        MessageBanner(
          widget.payload.qrPayload != null
              ? 'Bu düğme e-Fatura QR bilgisini (alıcının kimlik numarası olmadan) '
                    'sunucuya gönderir.'
              : 'Bu düğme yalnızca maskelenmiş metni sunucuya gönderir; '
                    'orijinal metin gönderilmez.',
          kind: MessageBannerKind.info,
        ),
        const SizedBox(height: AppSpacing.s),
        OutlinedButton(
          key: const Key('send_to_server_button'),
          onPressed: _sending ? null : () => unawaited(_send()),
          child: Text(_sending ? 'Gönderiliyor…' : 'Sunucuya gönder (debug)'),
        ),
        if (_error != null) ...[
          const SizedBox(height: AppSpacing.s),
          MessageBanner(_error!),
        ],
        if (result != null) ...[
          const SizedBox(height: AppSpacing.s),
          _ResultCard(result: result),
        ],
      ],
    );
  }
}

class _ResultCard extends StatelessWidget {
  const _ResultCard({required this.result});

  final ExtractionResult result;

  static const _fieldLabels = {
    'merchant': 'İşyeri',
    'date': 'Tarih',
    'time': 'Saat',
    'total': 'Toplam',
    'payment_method': 'Ödeme',
    'installment_count': 'Taksit',
    'items': 'Kalemler',
  };

  static const categoryLabels = {
    'GROCERY': 'Market',
    'FOOD_DRINK': 'Yeme-İçme',
    'TRANSPORT': 'Ulaşım',
    'FUEL': 'Yakıt',
    'CLOTHING': 'Giyim',
    'TECHNOLOGY': 'Teknoloji',
    'HOME': 'Ev & Yaşam',
    'HEALTH_CARE': 'Sağlık & Kişisel Bakım',
    'ENTERTAINMENT': 'Eğlence',
    'SUBSCRIPTION': 'Abonelik',
    'EDUCATION': 'Eğitim',
    'BILLS': 'Fatura & Hizmetler',
    'OTHER': 'Diğer',
  };

  static const _matchLabels = {
    'USER_ALIAS': 'senin takma adın',
    'GLOBAL_ALIAS': 'bilinen işyeri',
    'FUZZY': 'benzer isim',
    'NEW': 'yeni (tanınmadı)',
    'NONE': 'işyeri adı yok',
  };

  static const _sourceLabels = {
    'USER_RULE': 'senin kuralın',
    'MERCHANT_DEFAULT': 'işyerinin varsayılanı',
    'LLM': 'yapay zekâ',
    'FALLBACK': 'tahmin yok',
  };

  @override
  Widget build(BuildContext context) {
    final lines = <String>[
      result.usedQr
          ? 'Kaynak: e-Fatura QR'
                '${result.aiUsed ? ' + metin (yapay zekâ)' : ' (yapay zekâ kullanılmadı)'}'
          : 'Kaynak: fiş metni (yapay zekâ)',
      'İşyeri: ${result.merchant ?? '—'}',
      'Tarih: ${result.date ?? '—'}',
      'Toplam: ${result.total ?? '—'} TL',
      'Kalem sayısı: ${result.itemCount}',
      'İşyeri önerisi: ${result.merchantName ?? '—'} '
          '(${_matchLabels[result.merchantMatch] ?? result.merchantMatch})',
      'Kategori önerisi: '
          '${categoryLabels[result.categoryKey] ?? result.categoryKey} '
          '(${_sourceLabels[result.categorySource] ?? result.categorySource})',
    ];
    final confidence = result.confidence.entries
        .map((e) => '${_fieldLabels[e.key] ?? e.key}: ${e.value}')
        .join('  ·  ');
    return Container(
      key: const Key('server_result'),
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.m),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.control,
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final line in lines) Text(line, style: AppTextStyles.bodyS),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Güven: $confidence',
            style: AppTextStyles.caption.copyWith(color: AppColors.textMuted),
          ),
        ],
      ),
    );
  }
}
