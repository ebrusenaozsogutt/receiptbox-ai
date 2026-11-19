import 'dart:async';

import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../../core/networking/api_error.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_dimens.dart';
import '../../../../core/theme/app_text_styles.dart';
import '../../../../core/widgets/empty_state.dart';
import '../../../../core/widgets/message_banner.dart';
import '../../../transactions/data/transactions_providers.dart';
import '../../data/capture_providers.dart';
import 'fields_card.dart';
import 'review_controller.dart';
import 'review_widgets.dart';

/// "Fişi kontrol et" (Figma "02 · Fiş Kontrol"): the receipt was read on the phone and by the
/// server; the user looks at it, corrects what is wrong and saves it as a purchase.
class ReviewScreen extends ConsumerStatefulWidget {
  const ReviewScreen({super.key});

  @override
  ConsumerState<ReviewScreen> createState() => _ReviewScreenState();
}

class _ReviewScreenState extends ConsumerState<ReviewScreen> {
  String? _problem;
  bool _started = false;

  @override
  Widget build(BuildContext context) {
    final flow = ref.watch(captureFlowProvider);
    final review = ref.watch(reviewControllerProvider);

    // The capture finished: this screen takes over the outcome (and the kept image).
    if (!_started && flow is CaptureDone) {
      _started = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        final result = ref.read(captureFlowProvider.notifier).handOver();
        if (result != null) {
          unawaited(ref.read(reviewControllerProvider.notifier).start(result));
        }
      });
    }

    final Widget body;
    if (review.phase == ReviewPhase.idle) {
      body = switch (flow) {
        CaptureFailed(:final message, :final retryRoute) => EmptyState(
          icon: Icons.error_outline,
          title: 'Okunamadı',
          message: message,
          actionLabel: 'Tekrar dene',
          onAction: () => retryRoute == '/home'
              ? context.go(retryRoute)
              : context.pushReplacement(retryRoute),
        ),
        CaptureIdle() => const EmptyState(
          icon: Icons.receipt_long_outlined,
          title: 'Gösterilecek bir şey yok',
          message: 'Önce bir fiş veya fatura ekle.',
        ),
        _ => const _Working(message: 'Yazı telefonunda okunuyor…'),
      };
      return _frame(context, body, review, interactive: false);
    }
    if (review.phase == ReviewPhase.extracting) {
      return _frame(
        context,
        _Working(
          message: 'Fiş okunuyor… Bu en fazla bir dakika sürebilir.',
          onCancel: _cancel,
        ),
        review,
        interactive: false,
      );
    }
    return _frame(context, _form(review), review, interactive: true);
  }

  // ---- frame: app bar + body + action bar ---------------------------------------------------

  Widget _frame(
    BuildContext context,
    Widget body,
    ReviewState review, {
    required bool interactive,
  }) {
    final saving = review.phase == ReviewPhase.saving;
    return PopScope(
      canPop: !interactive,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) unawaited(_leave());
      },
      child: Scaffold(
        backgroundColor: AppColors.bg,
        body: SafeArea(
          child: Column(
            children: [
              _AppBar(onBack: interactive && !saving ? _leave : _backPlain),
              Expanded(child: body),
              if (interactive)
                _ActionBar(
                  saving: saving,
                  canSave: review.form?.canSave ?? false,
                  onCancel: _leave,
                  onSave: _save,
                ),
            ],
          ),
        ),
      ),
    );
  }

  void _backPlain() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go('/home');
    }
  }

  Widget _form(ReviewState review) {
    final form = review.form!;
    final controller = ref.read(reviewControllerProvider.notifier);
    final payload = review.payload!;
    return ListView(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.screenH,
        AppSpacing.s,
        AppSpacing.screenH,
        AppSpacing.xxl,
      ),
      children: [
        ReceiptPreviewCard(
          image: review.retainedImage,
          isPdf: review.retainedIsPdf,
          isQr: payload.qrPayload != null,
        ),
        const SizedBox(height: AppSpacing.m),
        ReviewBanner(pending: form.pendingChecks, notice: review.notice),
        if (_problem != null) ...[
          const SizedBox(height: AppSpacing.m),
          MessageBanner(_problem!),
        ],
        const SizedBox(height: AppSpacing.m),
        FieldsCard(
          form: form,
          onMerchant: controller.setMerchant,
          onDate: controller.setDate,
          onTime: controller.setTime,
          onTotal: controller.setTotal,
          onCategory: controller.setCategory,
          onChannel: controller.setChannel,
        ),
        const SizedBox(height: AppSpacing.m),
        ItemsCard(
          lines: form.lines,
          totalMinor: form.totalMinor,
          flagged: form.linesFlagged,
          onChanged: controller.setLines,
        ),
        if (kDebugMode && review.result != null) ...[
          const SizedBox(height: AppSpacing.m),
          TextButton(
            key: const Key('debug_result_link'),
            onPressed: () {
              ref
                  .read(captureFlowProvider.notifier)
                  .showForDebug(review.result!);
              unawaited(context.push('/capture/result'));
            },
            child: const Text('Okunan bilgileri göster (debug)'),
          ),
        ],
      ],
    );
  }

  // ---- actions --------------------------------------------------------------------------------

  /// Cancel while the receipt is still being read.
  Future<void> _cancel() async {
    await ref.read(reviewControllerProvider.notifier).discard();
    if (mounted) _backPlain();
  }

  /// "Vazgeç" / back: asks, then rejects the receipt and deletes the kept image.
  Future<void> _leave() async {
    final leave = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Kaydetmeden çıkılsın mı?'),
        content: const Text('Bu fiş kaydedilmeyecek ve eklediğin bilgiler silinecek.'),
        actions: [
          TextButton(
            key: const Key('leave_stay'),
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Devam et'),
          ),
          TextButton(
            key: const Key('leave_confirm'),
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Çık'),
          ),
        ],
      ),
    );
    if (leave != true || !mounted) return;
    await ref.read(reviewControllerProvider.notifier).discard();
    if (mounted) context.go('/home');
  }

  Future<void> _save() async {
    final controller = ref.read(reviewControllerProvider.notifier);
    var remember = false;
    if (controller.categoryWasChanged) {
      // Asked BEFORE saving: the answer goes with the confirm request.
      final answer = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Bu mağaza için hep böyle olsun mu?'),
          content: Text(
            'Bu mağazadan yaptığın sonraki alışverişler otomatik olarak '
            '"${ref.read(reviewControllerProvider).form!.category.label}" kategorisine girsin.',
          ),
          actions: [
            TextButton(
              key: const Key('remember_no'),
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('Sadece bu sefer'),
            ),
            TextButton(
              key: const Key('remember_yes'),
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: const Text('Evet, hep böyle'),
            ),
          ],
        ),
      );
      if (answer == null || !mounted) return; // dialog dismissed: nothing is saved
      remember = answer;
    }

    setState(() => _problem = null);
    final messenger = ScaffoldMessenger.of(context);
    final router = GoRouter.of(context);
    try {
      final outcome = await controller.save(rememberCategory: remember);
      ref.invalidate(purchaseListProvider);
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            outcome.imageUploaded == false
                ? 'Harcama kaydedildi ama fiş görseli yüklenemedi.'
                : 'Harcama kaydedildi.',
          ),
        ),
      );
      router.go('/transactions');
    } on ApiError catch (error) {
      if (mounted) setState(() => _problem = error.message);
    } on Object {
      if (mounted) setState(() => _problem = 'Kaydedilemedi. Tekrar dene.');
    }
  }
}

/// The custom app bar: a rounded back button, the title and a short hint.
class _AppBar extends StatelessWidget {
  const _AppBar({required this.onBack});

  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.screenH,
        AppSpacing.l,
        AppSpacing.screenH,
        AppSpacing.s,
      ),
      child: Row(
        children: [
          Material(
            color: AppColors.surface,
            shape: RoundedRectangleBorder(
              borderRadius: AppRadius.control,
              side: const BorderSide(color: AppColors.border),
            ),
            child: InkWell(
              key: const Key('review_back'),
              customBorder: RoundedRectangleBorder(
                borderRadius: AppRadius.control,
              ),
              onTap: onBack,
              child: const SizedBox(
                width: AppSizes.iconButton,
                height: AppSizes.iconButton,
                child: Icon(Icons.arrow_back, color: AppColors.text),
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.m),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Fişi kontrol et', style: AppTextStyles.titleL),
                Text(
                  'Yanlış olan alanı düzeltip kaydet',
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

/// The bottom bar: "Vazgeç" (secondary) and "Kaydet" (primary).
class _ActionBar extends StatelessWidget {
  const _ActionBar({
    required this.saving,
    required this.canSave,
    required this.onCancel,
    required this.onSave,
  });

  final bool saving;
  final bool canSave;
  final VoidCallback onCancel;
  final VoidCallback onSave;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.screenH,
        vertical: AppSpacing.m,
      ),
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        children: [
          Expanded(
            child: OutlinedButton(
              key: const Key('review_cancel'),
              onPressed: saving ? null : onCancel,
              child: const Text('Vazgeç'),
            ),
          ),
          const SizedBox(width: AppSpacing.m),
          Expanded(
            child: FilledButton(
              key: const Key('review_save'),
              onPressed: saving || !canSave ? null : onSave,
              child: saving
                  ? const SizedBox(
                      width: AppSizes.iconS,
                      height: AppSizes.iconS,
                      child: CircularProgressIndicator(
                        strokeWidth: AppSizes.progressThickness - 1,
                      ),
                    )
                  : const Text('Kaydet'),
            ),
          ),
        ],
      ),
    );
  }
}

class _Working extends StatelessWidget {
  const _Working({required this.message, this.onCancel});

  final String message;
  final VoidCallback? onCancel;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(
            width: AppSizes.progressSize,
            height: AppSizes.progressSize,
            child: CircularProgressIndicator(),
          ),
          const SizedBox(height: AppSpacing.l),
          Text(
            message,
            style: AppTextStyles.body.copyWith(color: AppColors.textMuted),
            textAlign: TextAlign.center,
          ),
          if (onCancel != null) ...[
            const SizedBox(height: AppSpacing.xxl),
            OutlinedButton(
              key: const Key('review_extract_cancel'),
              onPressed: onCancel,
              child: const Text('İptal'),
            ),
          ],
        ],
      ),
    );
  }
}
