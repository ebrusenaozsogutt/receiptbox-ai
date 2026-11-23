import 'dart:async';

import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../../core/networking/api_error.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_dimens.dart';
import '../../../../core/theme/app_text_styles.dart';
import '../../../../core/utils/date_format.dart';
import '../../../../core/utils/money_format.dart';
import '../../../../core/widgets/empty_state.dart';
import '../../../../core/widgets/match_badge.dart';
import '../../../../core/widgets/message_banner.dart';
import '../../../../core/widgets/review_badge.dart';
import '../../../installments/data/installment_providers.dart';
import '../../../installments/presentation/installment_widgets.dart';
import '../../../matching/data/matching_providers.dart';
import '../../../matching/domain/match_models.dart';
import '../../../matching/presentation/match_sheet.dart';
import '../../../matching/presentation/merge_feedback.dart';
import '../../../transactions/data/transactions_providers.dart';
import '../../data/capture_providers.dart';
import '../../domain/bank_models.dart';
import '../review/review_widgets.dart';
import 'bank_import_controller.dart';

/// "Banka ekran görüntüsü" (P08): the rows read from a bank screenshot, to select, correct and
/// save. Only the masked text of the screenshot was sent; the image is deleted after reading.
class BankImportScreen extends ConsumerStatefulWidget {
  const BankImportScreen({super.key});

  @override
  ConsumerState<BankImportScreen> createState() => _BankImportScreenState();
}

class _BankImportScreenState extends ConsumerState<BankImportScreen> {
  String? _problem;
  bool _started = false;

  @override
  Widget build(BuildContext context) {
    final flow = ref.watch(captureFlowProvider);
    final import = ref.watch(bankImportControllerProvider);

    // The capture finished: this screen takes over the outcome.
    if (!_started && flow is CaptureDone) {
      _started = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        final result = ref.read(captureFlowProvider.notifier).handOver();
        if (result != null) {
          unawaited(
            ref.read(bankImportControllerProvider.notifier).start(result),
          );
        }
      });
    }

    final Widget body;
    var showBar = false;
    if (import.phase == BankPhase.idle) {
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
          icon: Icons.account_balance_outlined,
          title: 'Gösterilecek bir şey yok',
          message: 'Önce bir banka ekran görüntüsü ekle.',
        ),
        _ => const _Working(message: 'Yazı telefonunda okunuyor…'),
      };
    } else if (import.phase == BankPhase.extracting) {
      body = _Working(
        message: 'Satırlar okunuyor… Bu en fazla bir dakika sürebilir.',
        onCancel: _cancelReading,
      );
    } else if (import.phase == BankPhase.failed) {
      body = _failure(import);
    } else {
      body = _rows(import);
      showBar = true;
    }

    return PopScope(
      canPop: !showBar,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) unawaited(_leave());
      },
      child: Scaffold(
        backgroundColor: AppColors.bg,
        body: SafeArea(
          child: Column(
            children: [
              _Header(onBack: showBar ? _leave : _plainBack),
              Expanded(child: body),
              if (showBar) _actionBar(import),
            ],
          ),
        ),
      ),
    );
  }

  void _plainBack() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go('/home');
    }
  }

  Future<void> _cancelReading() async {
    await ref.read(bankImportControllerProvider.notifier).discard();
    if (mounted) _plainBack();
  }

  Widget _failure(BankImportState import) {
    final code = import.errorCode;
    final consentOff =
        code == 'AI_CONSENT_OFF' || code == 'AI_CONSENT_REQUIRED';
    final notSupported = code == 'BANK_SCREEN_NOT_SUPPORTED';
    return EmptyState(
      icon: notSupported
          ? Icons.account_balance_wallet_outlined
          : Icons.error_outline,
      title: notSupported ? 'Bu ekran kart hareketi değil' : 'Okunamadı',
      message: import.errorMessage,
      actionLabel: consentOff
          ? "Ayarlar'a git"
          : notSupported
          ? 'Başka ekran seç'
          : 'Tekrar dene',
      onAction: () {
        if (consentOff) {
          unawaited(context.push('/settings'));
        } else if (notSupported) {
          _plainBack();
        } else {
          unawaited(ref.read(bankImportControllerProvider.notifier).retry());
        }
      },
    );
  }

  // ---- the rows ----------------------------------------------------------------------------

  Widget _rows(BankImportState import) {
    final controller = ref.read(bankImportControllerProvider.notifier);
    final purchases = import.purchases;
    final selectedCount = import.rows
        .where((r) => import.selected.contains(r.observationId))
        .length;
    return ListView(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.screenH,
        AppSpacing.s,
        AppSpacing.screenH,
        AppSpacing.xxl,
      ),
      children: [
        const MessageBanner(
          'Ekran görüntüsü telefonundan çıkmadı. Yalnızca kişisel bilgileri '
          'gizlenmiş metin okundu.',
          kind: MessageBannerKind.info,
        ),
        if (_problem != null) ...[
          const SizedBox(height: AppSpacing.s),
          MessageBanner(_problem!),
        ],
        const SizedBox(height: AppSpacing.m),
        _BankPicker(
          bank: import.bank,
          onChanged: (bank) => controller.changeBank(bank),
        ),
        const SizedBox(height: AppSpacing.m),
        if (purchases.isEmpty && import.possibleRefunds.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: AppSpacing.xxl),
            child: import.duplicates.isNotEmpty
                ? const EmptyState(
                    icon: Icons.check_circle_outline,
                    title: 'Yeni harcama yok',
                    message:
                        'Bu görüntüdeki satırların hepsi daha önce eklenmiş.',
                  )
                : const EmptyState(
                    icon: Icons.receipt_long_outlined,
                    title: 'Harcama satırı bulunamadı',
                    message:
                        'Bu görüntüde kaydedilecek bir harcama görünmüyor. '
                        'Kart hareketlerinin listesini seçmeyi dene.',
                  ),
          )
        else ...[
          Row(
            children: [
              Expanded(
                child: Text(
                  '${purchases.length} harcama okundu · $selectedCount seçili',
                  key: const Key('bank_summary'),
                  style: AppTextStyles.bodyS.copyWith(
                    color: AppColors.textMuted,
                  ),
                ),
              ),
              TextButton(
                key: const Key('bank_select_all'),
                onPressed: () =>
                    controller.selectAll(selectedCount < purchases.length),
                child: Text(
                  selectedCount < purchases.length
                      ? 'Tümünü seç'
                      : 'Seçimi kaldır',
                ),
              ),
            ],
          ),
          for (final row in purchases) _rowCard(import, row),
        ],
        if (import.possibleRefunds.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.l),
          Text(
            'Olası iadeler (${import.possibleRefunds.length})',
            style: AppTextStyles.titleS,
          ),
          const SizedBox(height: AppSpacing.xxs),
          Text(
            'Bunlar harcama olarak kaydedilmez; iade olabilecek satırlar '
            'olarak saklanır.',
            style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
          ),
          const SizedBox(height: AppSpacing.s),
          for (final row in import.possibleRefunds) _rowCard(import, row),
        ],
        if (import.duplicates.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.l),
          Text(
            'Daha önce eklenmiş (${import.duplicates.length})',
            style: AppTextStyles.titleS,
          ),
          const SizedBox(height: AppSpacing.xxs),
          Text(
            'Bu satırlar daha önce aldığın bir görüntüde de vardı; tekrar eklenmez.',
            style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
          ),
          const SizedBox(height: AppSpacing.s),
          for (final row in import.duplicates) _rowCard(import, row),
        ],
        if (import.skipped.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.l),
          Theme(
            data: Theme.of(context),
            child: ExpansionTile(
              key: const Key('skipped_section'),
              shape: const Border(),
              collapsedShape: const Border(),
              tilePadding: EdgeInsets.zero,
              title: Text(
                'Atlanan satırlar (${import.skipped.length})',
                style: AppTextStyles.titleS,
              ),
              children: [
                for (final row in import.skipped)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    title: Text(row.merchant, style: AppTextStyles.body),
                    subtitle: Text(
                      row.reasonLabel,
                      style: AppTextStyles.bodyS.copyWith(
                        color: AppColors.textMuted,
                      ),
                    ),
                    trailing: row.amountMinor == null
                        ? null
                        : Text(
                            formatMoneyTl(row.amountMinor!),
                            style: AppTextStyles.body.copyWith(
                              color: AppColors.textMuted,
                            ),
                          ),
                  ),
              ],
            ),
          ),
        ],
        if (kDebugMode && import.result != null) ...[
          const SizedBox(height: AppSpacing.m),
          TextButton(
            key: const Key('debug_result_link'),
            onPressed: () {
              ref
                  .read(captureFlowProvider.notifier)
                  .showForDebug(import.result!);
              unawaited(context.push('/capture/result'));
            },
            child: const Text('Okunan bilgileri göster (debug)'),
          ),
        ],
      ],
    );
  }

  Widget _rowCard(BankImportState import, BankRow row) {
    final edit = import.edits[row.observationId];
    final merchant = edit?.merchant ?? row.merchant;
    final amount = edit?.amountMinor ?? row.amountMinor;
    final date = edit?.date ?? row.date;
    final category = edit?.category ?? row.category;
    final selectable = row.isSelectable;
    final selected = import.selected.contains(row.observationId);
    final controller = ref.read(bankImportControllerProvider.notifier);
    final muted = !selectable;
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.s),
      child: Material(
        color: row.needsCheck && selectable
            ? AppColors.warningSoft
            : AppColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: AppRadius.card,
          side: BorderSide(
            color: selected ? AppColors.primary : AppColors.border,
          ),
        ),
        child: InkWell(
          key: Key('bank_row_${row.observationId}'),
          customBorder: RoundedRectangleBorder(borderRadius: AppRadius.card),
          onTap: selectable ? () => controller.toggle(row.observationId) : null,
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.m),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (selectable)
                  Checkbox(
                    key: Key('bank_row_check_${row.observationId}'),
                    value: selected,
                    onChanged: (_) => controller.toggle(row.observationId),
                  )
                else
                  const SizedBox(width: AppSpacing.m),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        merchant,
                        style: AppTextStyles.bodyStrong.copyWith(
                          color: muted ? AppColors.textMuted : AppColors.text,
                        ),
                      ),
                      const SizedBox(height: AppSpacing.xxs),
                      Text(
                        date == null ? 'Tarih okunamadı' : formatDateTr(date),
                        style: AppTextStyles.bodyS.copyWith(
                          color: date == null
                              ? AppColors.warning
                              : AppColors.textMuted,
                        ),
                      ),
                      const SizedBox(height: AppSpacing.xs),
                      Wrap(
                        spacing: AppSpacing.xs,
                        runSpacing: AppSpacing.xs,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          if (selectable) ...[
                            CategoryDot(color: category.color),
                            Text(
                              category.label,
                              style: AppTextStyles.caption.copyWith(
                                color: AppColors.textMuted,
                              ),
                            ),
                          ],
                          if (row.installmentLabel != null)
                            KeyedSubtree(
                              key: Key('installment_${row.observationId}'),
                              child: InstallmentBadge(
                                label: 'TAKSİT ${row.installmentLabel!}',
                              ),
                            ),
                          if (row.isPending)
                            const _Pill(
                              label: 'Bekliyor',
                              background: AppColors.surfaceAlt,
                              foreground: AppColors.textMuted,
                            ),
                          if (row.kind == BankRowKind.refund)
                            const _Pill(
                              label: 'Olası iade',
                              background: AppColors.successSoft,
                              foreground: AppColors.success,
                            ),
                          if (row.isDuplicate)
                            const _Pill(
                              label: 'Daha önce eklendi',
                              background: AppColors.surfaceAlt,
                              foreground: AppColors.textMuted,
                            ),
                          if (row.needsCheck && selectable) const ReviewBadge(),
                          if (row.match != null && selectable)
                            MatchBadge(
                              key: Key('match_badge_${row.observationId}'),
                              kind: row.match!.state == BankMatchState.auto
                                  ? MatchBadgeKind.matched
                                  : MatchBadgeKind.possible,
                            ),
                        ],
                      ),
                      if (row.installment != null && selectable) ...[
                        const SizedBox(height: AppSpacing.xs),
                        Text(
                          row.installment!.label,
                          key: Key('installment_hint_${row.observationId}'),
                          style: AppTextStyles.caption.copyWith(
                            color: AppColors.textMuted,
                          ),
                        ),
                      ],
                      if (row.match != null && selectable) ...[
                        const SizedBox(height: AppSpacing.xs),
                        Text(
                          row.match!.state == BankMatchState.auto
                              ? 'Mevcut harcamayla birleşecek: '
                                    '${row.match!.transaction.merchant}'
                              : 'Kaydedince sorulacak: '
                                    '${row.match!.transaction.merchant} ile aynı olabilir',
                          key: Key('match_hint_${row.observationId}'),
                          style: AppTextStyles.caption.copyWith(
                            color: AppColors.textMuted,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      '${row.isCredit ? '+' : ''}${formatMoneyTl(amount)}',
                      style: AppTextStyles.bodyStrong.copyWith(
                        color: row.isCredit
                            ? AppColors.success
                            : muted
                            ? AppColors.textMuted
                            : AppColors.text,
                      ),
                    ),
                    if (selectable)
                      IconButton(
                        key: Key('bank_row_edit_${row.observationId}'),
                        tooltip: 'Düzenle',
                        visualDensity: VisualDensity.compact,
                        icon: const Icon(
                          Icons.edit_outlined,
                          size: AppSizes.iconS,
                          color: AppColors.primary,
                        ),
                        onPressed: () => _edit(row),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  // ---- editing, leaving, saving --------------------------------------------------------------

  Future<void> _edit(BankRow row) async {
    final import = ref.read(bankImportControllerProvider);
    final current = import.edits[row.observationId] ?? const BankRowEdit();
    final result = await showModalBottomSheet<BankRowEdit>(
      context: context,
      isScrollControlled: true,
      useRootNavigator: true,
      builder: (_) => _EditSheet(row: row, edit: current),
    );
    if (result == null || !mounted) return;
    ref
        .read(bankImportControllerProvider.notifier)
        .edit(row.observationId, result);
  }

  Future<void> _leave() async {
    final leave = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Kaydetmeden çıkılsın mı?'),
        content: const Text(
          'Okunan satırlar kaydedilmeyecek. Ekran görüntüsü zaten saklanmıyor.',
        ),
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
    await ref.read(bankImportControllerProvider.notifier).discard();
    if (mounted) context.go('/home');
  }

  Widget _actionBar(BankImportState import) {
    final saving = import.phase == BankPhase.saving;
    final selected = import.rows
        .where(
          (r) => r.isSelectable && import.selected.contains(r.observationId),
        )
        .toList();
    final missingDate = selected
        .where((r) => (import.edits[r.observationId]?.date ?? r.date) == null)
        .length;
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.screenH,
        vertical: AppSpacing.m,
      ),
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (missingDate > 0)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.s),
              child: Text(
                '$missingDate satırın tarihi okunamadı: düzenleyip tarih ekle '
                'ya da seçimi kaldır.',
                key: const Key('bank_missing_date'),
                style: AppTextStyles.bodyS.copyWith(color: AppColors.warning),
              ),
            ),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  key: const Key('bank_cancel'),
                  onPressed: saving ? null : _leave,
                  child: const Text('Vazgeç'),
                ),
              ),
              const SizedBox(width: AppSpacing.m),
              Expanded(
                flex: 2,
                child: FilledButton(
                  key: const Key('bank_save'),
                  onPressed: saving || selected.isEmpty || missingDate > 0
                      ? null
                      : _save,
                  child: saving
                      ? const SizedBox(
                          width: AppSizes.iconS,
                          height: AppSizes.iconS,
                          child: CircularProgressIndicator(
                            strokeWidth: AppSizes.progressThickness - 1,
                          ),
                        )
                      : Text('Seçilenleri Kaydet (${selected.length})'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _save() async {
    setState(() => _problem = null);
    final messenger = ScaffoldMessenger.of(context);
    final router = GoRouter.of(context);
    final container = ProviderScope.containerOf(context);
    try {
      final outcome = await ref
          .read(bankImportControllerProvider.notifier)
          .save();
      ref
        ..invalidate(purchaseListProvider)
        ..invalidate(installmentScheduleProvider)
        ..invalidate(pendingMatchesProvider);

      // P09: rows that may be the same as a purchase you have are asked about, one by one. A
      // sheet that is closed leaves its question open (the Harcamalar screen shows it again).
      var joined = outcome.merged.length;
      var separate = 0;
      for (final group in groupByObservation(outcome.suggested).values) {
        if (!mounted) break;
        final answer = await showMatchSheet(context, group);
        if (answer == null) break;
        if (answer.merged) {
          joined++;
        } else {
          separate++;
        }
      }
      ref
        ..invalidate(purchaseListProvider)
        ..invalidate(installmentScheduleProvider)
        ..invalidate(pendingMatchesProvider);

      final parts = [
        '${outcome.created + separate} harcama kaydedildi',
        if (joined > 0) '$joined satır mevcut harcamayla birleşti',
        if (outcome.linked > 0)
          '${outcome.linked} taksit mevcut alışverişe bağlandı',
        if (outcome.skipped > 0) '${outcome.skipped} satır kaydedilemedi',
      ];
      final text = '${parts.join(', ')}.';
      if (outcome.merged.isEmpty) {
        messenger.showSnackBar(SnackBar(content: Text(text)));
      } else {
        showMergedSnackBar(
          messenger: messenger,
          container: container,
          message: text,
          merges: outcome.merged,
        );
      }
      router.go('/transactions');
    } on ApiError catch (error) {
      if (mounted) setState(() => _problem = error.message);
    } on Object {
      if (mounted) setState(() => _problem = 'Kaydedilemedi. Tekrar dene.');
    }
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.onBack});

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
              key: const Key('bank_back'),
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
                Text('Banka ekran görüntüsü', style: AppTextStyles.titleL),
                Text(
                  'Kaydedilecek satırları seç',
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

/// "Banka: Garanti BBVA ▾": the phone's guess, which the user can change.
class _BankPicker extends StatelessWidget {
  const _BankPicker({required this.bank, required this.onChanged});

  final BankKey? bank;
  final ValueChanged<BankKey?> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text(
          'Banka',
          style: AppTextStyles.label.copyWith(color: AppColors.textMuted),
        ),
        const SizedBox(width: AppSpacing.m),
        // The value is text: a null value would be taken for "the menu was dismissed".
        PopupMenuButton<String>(
          key: const Key('bank_chip'),
          onSelected: (value) => onChanged(
            BankKey.values.where((b) => b.wireName == value).firstOrNull,
          ),
          itemBuilder: (_) => [
            for (final option in BankKey.values)
              PopupMenuItem(
                key: Key('bank_option_${option.wireName}'),
                value: option.wireName,
                child: Text(option.label),
              ),
            const PopupMenuItem(
              key: Key('bank_option_other'),
              value: 'other',
              child: Text('Diğer banka'),
            ),
          ],
          child: Container(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.m,
              vertical: AppSpacing.s,
            ),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: AppRadius.circular(AppRadius.pill),
              border: Border.all(color: AppColors.border),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(bank?.label ?? 'Diğer banka', style: AppTextStyles.label),
                const SizedBox(width: AppSpacing.xxs),
                const Icon(Icons.expand_more, size: AppSizes.iconS),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _Pill extends StatelessWidget {
  const _Pill({
    required this.label,
    required this.background,
    required this.foreground,
  });

  final String label;
  final Color background;
  final Color foreground;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.s,
        vertical: AppSpacing.badgeV,
      ),
      decoration: BoxDecoration(
        color: background,
        borderRadius: AppRadius.circular(AppRadius.pill),
      ),
      child: Text(
        label,
        style: AppTextStyles.overline.copyWith(color: foreground),
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
            TextButton(
              key: const Key('bank_extract_cancel'),
              onPressed: onCancel,
              child: const Text('İptal'),
            ),
          ],
        ],
      ),
    );
  }
}

/// The sheet to correct one row: merchant, amount, date and category.
class _EditSheet extends StatefulWidget {
  const _EditSheet({required this.row, required this.edit});

  final BankRow row;
  final BankRowEdit edit;

  @override
  State<_EditSheet> createState() => _EditSheetState();
}

class _EditSheetState extends State<_EditSheet> {
  late final _merchant = TextEditingController(
    text: widget.edit.merchant ?? widget.row.merchant,
  );
  late final _amount = TextEditingController(
    text: formatMoneyMinor(widget.edit.amountMinor ?? widget.row.amountMinor),
  );
  late DateTime? _date = widget.edit.date ?? widget.row.date;
  late var _category = widget.edit.category ?? widget.row.category;

  @override
  void dispose() {
    _merchant.dispose();
    _amount.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _date ?? DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime.now().add(const Duration(days: 1)),
      locale: const Locale('tr', 'TR'),
    );
    if (picked != null) setState(() => _date = picked);
  }

  Future<void> _pickCategory() async {
    final picked = await pickCategory(context, _category);
    if (picked != null) setState(() => _category = picked);
  }

  @override
  Widget build(BuildContext context) {
    final minor = parseMoneyToMinor(_amount.text);
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
      child: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.screenH),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('Satırı düzenle', style: AppTextStyles.titleM),
              const SizedBox(height: AppSpacing.m),
              TextField(
                key: const Key('bank_edit_merchant'),
                controller: _merchant,
                decoration: const InputDecoration(labelText: 'Mağaza'),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: AppSpacing.m),
              TextField(
                key: const Key('bank_edit_amount'),
                controller: _amount,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                inputFormatters: [
                  FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]')),
                ],
                decoration: const InputDecoration(
                  labelText: 'Tutar',
                  suffixText: 'TL',
                ),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: AppSpacing.m),
              ListTile(
                key: const Key('bank_edit_date'),
                contentPadding: EdgeInsets.zero,
                title: const Text('Tarih'),
                subtitle: Text(_date == null ? 'Seç' : formatDateTr(_date!)),
                trailing: const Icon(Icons.calendar_today_outlined),
                onTap: _pickDate,
              ),
              ListTile(
                key: const Key('bank_edit_category'),
                contentPadding: EdgeInsets.zero,
                title: const Text('Kategori'),
                subtitle: Text(_category.label),
                leading: CategoryDot(color: _category.color),
                trailing: const Icon(Icons.expand_more),
                onTap: _pickCategory,
              ),
              const SizedBox(height: AppSpacing.m),
              FilledButton(
                key: const Key('bank_edit_save'),
                onPressed:
                    _merchant.text.trim().isEmpty || minor == null || minor <= 0
                    ? null
                    : () => Navigator.of(context).pop(
                        BankRowEdit(
                          merchant: _merchant.text.trim(),
                          date: _date,
                          amountMinor: minor,
                          category: _category,
                        ),
                      ),
                child: const Text('Tamam'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
