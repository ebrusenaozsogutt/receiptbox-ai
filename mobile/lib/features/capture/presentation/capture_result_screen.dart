import 'dart:async';

import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/privacy/pii_masker.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/loading_view.dart';
import '../../../core/widgets/message_banner.dart';
import '../data/capture_providers.dart';
import '../domain/capture_payload.dart';
import 'server_extraction_panel.dart';

/// What the phone read from the picture, AFTER masking. In P04 nothing is sent anywhere:
/// P05 sends [CapturePayload] to the backend, P07 turns it into a review screen.
class CaptureResultScreen extends ConsumerStatefulWidget {
  const CaptureResultScreen({super.key});

  @override
  ConsumerState<CaptureResultScreen> createState() =>
      _CaptureResultScreenState();
}

class _CaptureResultScreenState extends ConsumerState<CaptureResultScreen> {
  late final CaptureFlow _flow;

  @override
  void initState() {
    super.initState();
    // Saved now: `ref` must not be used inside dispose().
    _flow = ref.read(captureFlowProvider.notifier);
  }

  @override
  void dispose() {
    // Do not keep the text in memory after leaving the screen. (Not during dispose itself:
    // changing a provider while the tree is being torn down is not allowed.)
    Future.microtask(_flow.reset);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(captureFlowProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Okunan bilgiler')),
      body: SafeArea(
        child: switch (state) {
          CaptureIdle() => const EmptyState(
            icon: Icons.document_scanner_outlined,
            title: 'Gösterilecek bir şey yok',
            message: 'Önce bir fiş veya ekran görüntüsü ekle.',
          ),
          CaptureProcessing() => const LoadingView(
            message: 'Yazı telefonunda okunuyor…',
          ),
          CaptureFailed(:final message, :final retryRoute) => EmptyState(
            icon: Icons.error_outline,
            title: 'Okunamadı',
            message: message,
            actionLabel: 'Tekrar dene',
            onAction: () => retryRoute == '/home'
                ? context.go(retryRoute)
                : context.pushReplacement(retryRoute),
          ),
          CaptureDone(:final result) => _ResultBody(result: result),
        },
      ),
    );
  }
}

class _ResultBody extends StatelessWidget {
  const _ResultBody({required this.result});

  final CaptureResult result;

  @override
  Widget build(BuildContext context) {
    final payload = result.payload;
    final original = result.debugOriginalText;
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.screenH),
      children: [
        Text(
          payload.kind == CaptureKind.receipt
              ? 'Fiş / fatura'
              : 'Banka ekran görüntüsü',
          style: AppTextStyles.titleM,
        ),
        const SizedBox(height: AppSpacing.xxs),
        Text(
          result.pageCount > 1
              ? '${result.pageCount} sayfa okundu'
              : '1 sayfa okundu',
          style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
        ),
        const SizedBox(height: AppSpacing.m),
        if (payload.qrPayload != null) ...[
          const MessageBanner(
            'e-Fatura QR kodu bulundu. Tutar ve tarih QR kodundan da okunabilecek.',
            kind: MessageBannerKind.info,
          ),
          const SizedBox(height: AppSpacing.s),
        ],
        MessageBanner(_maskingSummary(result), kind: MessageBannerKind.info),
        const SizedBox(height: AppSpacing.l),
        Text('Maskelenmiş metin', style: AppTextStyles.label),
        const SizedBox(height: AppSpacing.xs),
        _TextBox(
          key: const Key('masked_text'),
          text: payload.maskedText.isEmpty
              ? '(Yazı bulunamadı; yalnızca QR kodu okundu.)'
              : payload.maskedText,
        ),
        if (kDebugMode && original != null) ...[
          const SizedBox(height: AppSpacing.l),
          Text('Orijinal metin (yalnızca debug)', style: AppTextStyles.label),
          const SizedBox(height: AppSpacing.xs),
          const MessageBanner(
            'Bu bölüm yalnızca debug sürümünde görünür. Orijinal metin hiçbir yere '
            'kaydedilmez veya gönderilmez.',
          ),
          const SizedBox(height: AppSpacing.s),
          _TextBox(key: const Key('original_text'), text: original),
        ],
        const SizedBox(height: AppSpacing.l),
        const MessageBanner(
          'Bu bilgiler kendiliğinden hiçbir yere gönderilmez. Sonraki aşamada '
          'incelenip kaydedilecek.',
          kind: MessageBannerKind.info,
        ),
        if (kDebugMode && payload.kind == CaptureKind.receipt) ...[
          const SizedBox(height: AppSpacing.l),
          ServerExtractionPanel(payload: payload),
        ],
        const SizedBox(height: AppSpacing.xxl),
        FilledButton(
          key: const Key('result_done_button'),
          onPressed: () => context.go('/home'),
          child: const Text('Bitti'),
        ),
      ],
    );
  }

  static String _maskingSummary(CaptureResult result) {
    if (result.maskedTotal == 0) return 'Gizlenmesi gereken bilgi bulunmadı.';
    final parts = [
      for (final entry in result.maskedCounts.entries)
        if (entry.value > 0) '${entry.value} ${entry.key.turkishLabel}',
    ];
    return '${result.maskedTotal} hassas bilgi gizlendi: ${parts.join(', ')}.';
  }
}

extension on PiiType {
  String get turkishLabel => switch (this) {
    PiiType.iban => 'IBAN',
    PiiType.card => 'kart numarası',
    PiiType.tckn => 'T.C. kimlik no',
    PiiType.phone => 'telefon',
    PiiType.email => 'e-posta',
    PiiType.balance => 'bakiye satırı',
    PiiType.name => 'isim',
  };
}

class _TextBox extends StatelessWidget {
  const _TextBox({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(
        maxHeight: AppSizes.resultTextMaxHeight,
      ),
      padding: const EdgeInsets.all(AppSpacing.m),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.control,
        border: Border.all(color: AppColors.border),
      ),
      child: SingleChildScrollView(
        child: SizedBox(
          width: double.infinity,
          child: Text(text, style: AppTextStyles.bodyS),
        ),
      ),
    );
  }
}
