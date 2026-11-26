import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/utils/date_format.dart';
import '../../../core/utils/money_format.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../data/installment_providers.dart';
import '../domain/installment_models.dart';
import 'installment_widgets.dart';

/// "Taksitler": what is to be paid each month for the purchases bought in installments. These
/// are payments, NOT spending: a purchase is counted once, in the month it was bought.
class InstallmentScheduleScreen extends ConsumerWidget {
  const InstallmentScheduleScreen({super.key, this.focusMonth});

  /// "YYYY-MM": scroll to this month (P14: the assistant's "Taksitleri gör").
  final String? focusMonth;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final schedule = ref.watch(installmentScheduleProvider);
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(title: const Text('Taksitler')),
      body: SafeArea(
        child: schedule.when(
          loading: () => const LoadingView(),
          error: (error, _) => ErrorView(
            message: error is ApiError
                ? error.message
                : 'Taksitler yüklenemedi.',
            onRetry: () => ref.invalidate(installmentScheduleProvider),
          ),
          data: (data) => data.isEmpty
              ? const EmptyState(
                  icon: Icons.calendar_month_outlined,
                  title: 'Taksitli alışveriş yok',
                  message:
                      'Bir alışverişi "Taksitli" olarak kaydedersen ya da banka '
                      'ekranında taksit satırı görürsek aylık ödemeler burada '
                      'listelenir.',
                )
              : _ScheduleBody(schedule: data, focusMonth: focusMonth),
        ),
      ),
    );
  }
}

class _ScheduleBody extends StatefulWidget {
  const _ScheduleBody({required this.schedule, this.focusMonth});

  final InstallmentSchedule schedule;
  final String? focusMonth;

  @override
  State<_ScheduleBody> createState() => _ScheduleBodyState();
}

class _ScheduleBodyState extends State<_ScheduleBody> {
  final _focusKey = GlobalKey();

  static String _monthKey(DateTime month) =>
      '${month.year.toString().padLeft(4, '0')}-'
      '${month.month.toString().padLeft(2, '0')}';

  @override
  void initState() {
    super.initState();
    if (widget.focusMonth != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final target = _focusKey.currentContext;
        if (target != null && target.mounted) Scrollable.ensureVisible(target);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final schedule = widget.schedule;
    final months = schedule.months.where((m) => m.items.isNotEmpty).toList();
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.screenH),
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(AppSpacing.l),
          decoration: BoxDecoration(
            color: AppColors.primarySoft,
            borderRadius: AppRadius.card,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Kalan taksit toplamı',
                style: AppTextStyles.label.copyWith(color: AppColors.primary),
              ),
              const SizedBox(height: AppSpacing.xxs),
              Text(
                formatMoneyTl(schedule.remainingMinor),
                key: const Key('schedule_remaining'),
                style: AppTextStyles.display.copyWith(color: AppColors.primary),
              ),
              const SizedBox(height: AppSpacing.xxs),
              Text(
                'Bunlar ödemelerdir; harcama alışveriş ayında bir kez sayılır.',
                style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
              ),
            ],
          ),
        ),
        for (final month in months) ...[
          const SizedBox(height: AppSpacing.l),
          KeyedSubtree(
            // The first month needs no scrolling: scrolling to it would hide the
            // "Kalan taksit toplamı" card above it (found on the emulator).
            key:
                month != months.first &&
                    _monthKey(month.month) == widget.focusMonth
                ? _focusKey
                : null,
            child: _MonthSection(month: month),
          ),
        ],
        const SizedBox(height: AppSpacing.l),
        const _Legend(),
      ],
    );
  }
}

class _MonthSection extends StatelessWidget {
  const _MonthSection({required this.month});

  final ScheduleMonth month;

  @override
  Widget build(BuildContext context) {
    final key = '${month.month.year}-${month.month.month}';
    return Column(
      key: Key('schedule_month_$key'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                formatMonthTr(month.month),
                style: AppTextStyles.titleS,
              ),
            ),
            Text(
              formatMoneyTl(month.totalMinor),
              key: Key('schedule_total_$key'),
              style: AppTextStyles.bodyStrong,
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.s),
        Container(
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: AppRadius.card,
            border: Border.all(color: AppColors.border),
          ),
          child: Column(
            children: [
              for (var i = 0; i < month.items.length; i++)
                _ItemRow(item: month.items[i], first: i == 0),
            ],
          ),
        ),
      ],
    );
  }
}

class _ItemRow extends StatelessWidget {
  const _ItemRow({required this.item, required this.first});

  final ScheduleItem item;
  final bool first;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      key: Key('schedule_item_${item.transactionId}_${item.seq}'),
      onTap: () => context.push('/transactions/${item.transactionId}'),
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.l,
          vertical: AppSpacing.rowV,
        ),
        decoration: BoxDecoration(
          border: first
              ? null
              : const Border(top: BorderSide(color: AppColors.border)),
        ),
        child: Row(
          children: [
            PaymentDot(status: item.status),
            const SizedBox(width: AppSpacing.m),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(item.merchant, style: AppTextStyles.body),
                  Wrap(
                    spacing: AppSpacing.s,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Text(
                        'Taksit ${item.seq}/${item.count} · ${item.status.label}',
                        style: AppTextStyles.caption.copyWith(
                          color: AppColors.textMuted,
                        ),
                      ),
                      if (item.isEstimated) const EstimatedBadge(),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.s),
            Text(
              formatMoneyTl(item.amountMinor),
              style: AppTextStyles.bodyStrong,
            ),
          ],
        ),
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  const _Legend();

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: AppSpacing.l,
      runSpacing: AppSpacing.xs,
      children: [
        for (final status in PaymentStatus.values)
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              PaymentDot(status: status),
              const SizedBox(width: AppSpacing.xs),
              Text(
                status.label,
                style: AppTextStyles.caption.copyWith(
                  color: AppColors.textMuted,
                ),
              ),
            ],
          ),
      ],
    );
  }
}
