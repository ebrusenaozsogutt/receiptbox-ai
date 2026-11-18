import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/widgets/message_banner.dart';
import '../data/capture_providers.dart';
import '../domain/capture_payload.dart';
import 'capture_kind_sheet.dart';

/// "Galeriden Ekle" (the kind is asked after the photo is chosen) and
/// "Banka Ekran Görüntüsü" (the kind is fixed). Both open the system photo picker.
class PickImageScreen extends ConsumerStatefulWidget {
  const PickImageScreen({
    super.key,
    required this.title,
    required this.icon,
    required this.description,
    this.fixedKind,
    this.privacyNote,
  });

  const PickImageScreen.gallery({super.key})
    : title = 'Galeriden Ekle',
      icon = Icons.photo_library_outlined,
      description = 'Galerindeki bir fiş veya fatura fotoğrafını seç. Yazı telefonunda okunur.',
      fixedKind = null,
      privacyNote = null;

  const PickImageScreen.bank({super.key})
    : title = 'Banka Ekran Görüntüsü',
      icon = Icons.account_balance_outlined,
      description =
          'Banka uygulamasındaki harcama listesinin ekran görüntüsünü seç.',
      fixedKind = CaptureKind.bankScreenshot,
      privacyNote =
          'Ekran görüntüsü telefonundan çıkmaz. Yalnızca IBAN, kart no, bakiye gibi bilgileri '
          'silinmiş metin işlenir.';

  final String title;
  final IconData icon;
  final String description;
  final CaptureKind? fixedKind;
  final String? privacyNote;

  @override
  ConsumerState<PickImageScreen> createState() => _PickImageScreenState();
}

class _PickImageScreenState extends ConsumerState<PickImageScreen> {
  bool _picking = false;
  String? _problem;

  Future<void> _pick() async {
    if (_picking) return;
    setState(() {
      _picking = true;
      _problem = null;
    });
    try {
      final picked = await ref.read(galleryPickerProvider).pickImage();
      if (!mounted) return;
      if (picked == null) {
        setState(() => _picking = false);
        return;
      }
      final kind = widget.fixedKind ?? await askCaptureKind(context);
      if (!mounted) return;
      if (kind == null) {
        // The picked copy is not needed any more.
        unawaited(picked.file.delete().catchError((_) => picked.file));
        setState(() => _picking = false);
        return;
      }
      unawaited(
        ref
            .read(captureFlowProvider.notifier)
            .process(
              CaptureInput(
                file: picked.file,
                kind: kind,
                source: CaptureSource.gallery,
                captureDate: picked.modified,
              ),
            ),
      );
      context.pushReplacement('/capture/result');
    } on Object {
      if (!mounted) return;
      setState(() {
        _picking = false;
        _problem = 'Galeri açılamadı. Tekrar dene.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpacing.xxl),
            child: ConstrainedBox(
              constraints: const BoxConstraints(
                maxWidth: AppSizes.emptyStateMaxWidth,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(
                    widget.icon,
                    size: AppSizes.iconXl,
                    color: AppColors.primary,
                  ),
                  const SizedBox(height: AppSpacing.l),
                  Text(
                    widget.description,
                    style: AppTextStyles.body,
                    textAlign: TextAlign.center,
                  ),
                  if (widget.privacyNote != null) ...[
                    const SizedBox(height: AppSpacing.m),
                    MessageBanner(
                      widget.privacyNote!,
                      kind: MessageBannerKind.info,
                    ),
                  ],
                  if (_problem != null) ...[
                    const SizedBox(height: AppSpacing.m),
                    MessageBanner(_problem!),
                  ],
                  const SizedBox(height: AppSpacing.xxl),
                  FilledButton(
                    key: const Key('pick_image_button'),
                    onPressed: _picking ? null : _pick,
                    child: const Text('Fotoğraf seç'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
