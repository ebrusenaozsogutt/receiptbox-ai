import 'package:flutter_svg/flutter_svg.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/utils/date_format.dart';
import '../../../core/utils/money_format.dart';
import '../../analytics/domain/analytics_models.dart';
import '../../capture/presentation/review/review_widgets.dart' show CategoryDot;

/// The pieces of the home screen, built from the Figma frame "01 · Ana Sayfa".

/// "%8,8": one decimal with a comma, as Turkish writes it.
String percentTr(double value) =>
    '%${value.abs().toStringAsFixed(1).replaceAll('.', ',')}';

/// "↑ %8,8 · Ekim'e göre +1.520 TL", or a sentence when there is nothing to compare with.
String changeLabel(SpendingSummary spending) {
  final pct = spending.changePct;
  if (pct == null) {
    return spending.totalMinor == 0
        ? 'Bu ay henüz harcama yok'
        : '${monthDativeTr(spending.previousMonth)} göre karşılaştırma yok';
  }
  final change = spending.changeMinor;
  final arrow = change > 0
      ? '↑'
      : change < 0
      ? '↓'
      : '→';
  final sign = change > 0 ? '+' : '';
  return '$arrow ${percentTr(pct)} · ${monthDativeTr(spending.previousMonth)} '
      'göre $sign${formatMoneyWholeTl(change)}';
}

bool isSameMonth(DateTime a, DateTime b) =>
    a.year == b.year && a.month == b.month;

/// Header: greeting, month picker (left), settings and the bell (right).
class HomeHeader extends StatelessWidget {
  const HomeHeader({
    super.key,
    required this.month,
    required this.onPickMonth,
    required this.onBell,
  });

  final DateTime month;
  final VoidCallback onPickMonth;
  final VoidCallback onBell;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Merhaba 👋',
                style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
              ),
              const SizedBox(height: AppSpacing.xxxs),
              InkWell(
                key: const Key('home_month_picker'),
                onTap: onPickMonth,
                borderRadius: AppRadius.control,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      formatMonthTr(month),
                      key: const Key('home_month'),
                      style: AppTextStyles.titleL,
                    ),
                    const SizedBox(width: AppSpacing.xxs),
                    SvgPicture.asset(
                      'assets/icons/home_chevron_down.svg',
                      width: AppSizes.monthChevron,
                      height: AppSizes.monthChevron,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        IconButton(
          tooltip: 'Ayarlar',
          constraints: const BoxConstraints.tightFor(
            width: AppSizes.iconButton,
            height: AppSizes.iconButton,
          ),
          icon: const Icon(
            Icons.settings_outlined,
            size: AppSizes.icon,
            color: AppColors.textMuted,
          ),
          onPressed: () => context.push('/settings'),
        ),
        const SizedBox(width: AppSpacing.xs),
        Material(
          color: AppColors.surface,
          shape: RoundedRectangleBorder(
            borderRadius: AppRadius.circular(AppRadius.iconButtonBox),
            side: const BorderSide(color: AppColors.border),
          ),
          child: InkWell(
            key: const Key('home_bell'),
            customBorder: RoundedRectangleBorder(
              borderRadius: AppRadius.circular(AppRadius.iconButtonBox),
            ),
            onTap: onBell,
            child: SizedBox(
              width: AppSizes.iconButton,
              height: AppSizes.iconButton,
              child: Center(
                child: SvgPicture.asset(
                  'assets/icons/home_bell.svg',
                  width: AppSizes.bellIcon,
                  height: AppSizes.bellIcon,
                  semanticsLabel: 'Dikkat gerektirenler',
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// The dark teal card: the month's total and the change against the month before.
class SpendingHero extends StatelessWidget {
  const SpendingHero({super.key, required this.spending, required this.today});

  final SpendingSummary spending;
  final DateTime today;

  @override
  Widget build(BuildContext context) {
    final title = isSameMonth(spending.month, today)
        ? 'BU AYKİ HARCAMA'
        : '${upperTr(formatMonthTr(spending.month))} HARCAMASI';
    return Container(
      key: const Key('home_spending'),
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.xl),
      decoration: BoxDecoration(
        color: AppColors.primary,
        borderRadius: AppRadius.circular(AppRadius.xl),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: AppTextStyles.overline.copyWith(color: AppColors.onPrimary),
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            formatMoneyTl(spending.totalMinor),
            key: const Key('home_spending_total'),
            style: AppTextStyles.display.copyWith(color: AppColors.onPrimary),
          ),
          const SizedBox(height: AppSpacing.xs),
          Container(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.chipH,
              vertical: AppSpacing.chipV,
            ),
            decoration: BoxDecoration(
              color: AppColors.heroChip,
              borderRadius: AppRadius.circular(AppRadius.pill),
            ),
            child: Text(
              changeLabel(spending),
              key: const Key('home_change_chip'),
              style: AppTextStyles.caption.copyWith(color: AppColors.onPrimary),
            ),
          ),
        ],
      ),
    );
  }
}

/// A white card with the border and radius of the Figma cards.
class HomeCard extends StatelessWidget {
  const HomeCard({super.key, required this.child, this.padding});

  final Widget child;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: padding ?? const EdgeInsets.all(AppSpacing.l),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.card,
        border: Border.all(color: AppColors.border),
      ),
      child: child,
    );
  }
}

/// A thin rounded bar: [fraction] (0..1) of [color] on [background].
class ProgressTrack extends StatelessWidget {
  const ProgressTrack({
    super.key,
    required this.fraction,
    required this.color,
    required this.background,
    required this.height,
    required this.radius,
  });

  final double fraction;
  final Color color;
  final Color background;
  final double height;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: AppRadius.circular(radius),
      child: Container(
        height: height,
        color: background,
        alignment: Alignment.centerLeft,
        child: FractionallySizedBox(
          widthFactor: fraction.clamp(0.0, 1.0),
          heightFactor: 1,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: color,
              borderRadius: AppRadius.circular(radius),
            ),
          ),
        ),
      ),
    );
  }
}

/// "Kategoriler": the categories of the month with bars relative to the largest one.
class CategoryBreakdown extends StatelessWidget {
  const CategoryBreakdown({
    super.key,
    required this.categories,
    required this.onAll,
  });

  /// Most shown on the home screen; "Tümü" shows everything.
  static const int maxRows = 5;

  final List<CategoryAmount> categories;
  final VoidCallback onAll;

  @override
  Widget build(BuildContext context) {
    final rows = categories.take(maxRows).toList();
    final largest = rows.fold<int>(
      0,
      (m, c) => c.totalMinor > m ? c.totalMinor : m,
    );
    return HomeCard(
      key: const Key('home_categories'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text('Kategoriler', style: AppTextStyles.titleM)),
              InkWell(
                key: const Key('home_all_categories'),
                onTap: onAll,
                child: Text(
                  'Tümü',
                  style: AppTextStyles.label.copyWith(color: AppColors.primary),
                ),
              ),
            ],
          ),
          if (rows.isEmpty) ...[
            const SizedBox(height: AppSpacing.m),
            Text(
              'Bu ay henüz harcama yok.',
              style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
            ),
          ],
          for (final row in rows) ...[
            const SizedBox(height: AppSpacing.m),
            Column(
              key: Key('home_category_${row.category.key}'),
              children: [
                Row(
                  children: [
                    CategoryDot(color: row.category.color),
                    const SizedBox(width: AppSpacing.s),
                    Expanded(
                      child: Text(
                        row.category.label,
                        style: AppTextStyles.body,
                      ),
                    ),
                    Text(
                      formatMoneyWholeTl(row.totalMinor),
                      style: AppTextStyles.bodyStrong,
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.xs),
                ProgressTrack(
                  fraction: largest <= 0 ? 0 : row.totalMinor / largest,
                  color: row.category.color,
                  background: AppColors.surfaceAlt,
                  height: AppSizes.categoryTrack,
                  radius: AppRadius.track,
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

/// "Dikkat gerektirenler": budgets at 80 % or more (returns and warranties arrive with P12).
class AttentionSection extends StatelessWidget {
  const AttentionSection({
    super.key,
    required this.items,
    required this.onBudget,
  });

  final List<AttentionItem> items;
  final VoidCallback onBudget;

  @override
  Widget build(BuildContext context) {
    final budgets = [
      for (final item in items)
        if (item.budget != null) item.budget!,
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Dikkat gerektirenler', style: AppTextStyles.titleM),
        const SizedBox(height: AppSpacing.m),
        HomeCard(
          key: const Key('home_attention'),
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.l,
            vertical: AppSpacing.xxs,
          ),
          child: budgets.isEmpty
              ? Padding(
                  padding: const EdgeInsets.symmetric(vertical: AppSpacing.m),
                  child: Text(
                    'Şu an dikkat gerektiren bir şey yok.',
                    key: const Key('home_attention_empty'),
                    style: AppTextStyles.bodyS.copyWith(
                      color: AppColors.textMuted,
                    ),
                  ),
                )
              : Column(
                  children: [
                    for (var i = 0; i < budgets.length; i++)
                      _BudgetRow(
                        budget: budgets[i],
                        first: i == 0,
                        onTap: onBudget,
                      ),
                  ],
                ),
        ),
      ],
    );
  }
}

class _BudgetRow extends StatelessWidget {
  const _BudgetRow({
    required this.budget,
    required this.first,
    required this.onTap,
  });

  final BudgetUsage budget;
  final bool first;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final over = budget.state == BudgetState.over;
    final color = over ? AppColors.danger : AppColors.warning;
    final soft = over ? AppColors.dangerSoft : AppColors.warningSoft;
    return InkWell(
      key: Key('home_budget_${budget.category.key}'),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.m),
        decoration: BoxDecoration(
          border: first
              ? null
              : const Border(top: BorderSide(color: AppColors.border)),
        ),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '${budget.category.label} bütçesi',
                    style: AppTextStyles.bodyStrong,
                  ),
                ),
                Text(
                  '%${budget.pct} · ${formatMoneyWholeTl(budget.spentMinor).replaceAll(' TL', '')}'
                  ' / ${formatMoneyWholeTl(budget.limitMinor)}',
                  style: AppTextStyles.bodyS.copyWith(color: color),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.s),
            ProgressTrack(
              fraction: budget.pct / 100,
              color: color,
              background: soft,
              height: AppSizes.budgetTrack,
              radius: AppRadius.xs,
            ),
          ],
        ),
      ),
    );
  }
}

/// "Bu ay ödenecekler": the installment payments of the month and the next six months. These
/// are payments, never spending.
class PaymentsDueCard extends StatelessWidget {
  const PaymentsDueCard({
    super.key,
    required this.data,
    required this.today,
    required this.onPayment,
  });

  final HomeData data;
  final DateTime today;
  final ValueChanged<DuePayment> onPayment;

  @override
  Widget build(BuildContext context) {
    final title = isSameMonth(data.month, today)
        ? 'Bu ay ödenecekler'
        : '${formatMonthTr(data.month)} ödemeleri';
    final payments = data.duePayments;
    return HomeCard(
      key: const Key('home_due'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: AppTextStyles.titleM),
                    const SizedBox(height: AppSpacing.xxxs),
                    Text(
                      payments.isEmpty
                          ? 'Taksit yok'
                          : '${payments.length} taksit',
                      style: AppTextStyles.bodyS.copyWith(
                        color: AppColors.textMuted,
                      ),
                    ),
                  ],
                ),
              ),
              Text(
                formatMoneyTl(data.dueTotalMinor),
                key: const Key('home_due_total'),
                style: AppTextStyles.titleM.copyWith(color: AppColors.primary),
              ),
            ],
          ),
          for (final payment in payments) ...[
            const SizedBox(height: AppSpacing.m),
            _PaymentRow(payment: payment, onTap: () => onPayment(payment)),
          ],
          const SizedBox(height: AppSpacing.m),
          _NextMonths(months: data.nextMonths),
        ],
      ),
    );
  }
}

class _PaymentRow extends StatelessWidget {
  const _PaymentRow({required this.payment, required this.onTap});

  final DuePayment payment;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final initial = payment.merchant.trim().isEmpty
        ? '?'
        : payment.merchant.trim().characters.first.toUpperCase();
    final what = payment.category?.label ?? 'Taksit';
    return InkWell(
      key: Key('home_due_${payment.transactionId}_${payment.seq}'),
      onTap: onTap,
      child: Row(
        children: [
          Container(
            width: AppSizes.paymentAvatar,
            height: AppSizes.paymentAvatar,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: AppColors.primarySoft,
              borderRadius: AppRadius.circular(AppRadius.thumbnail),
            ),
            child: Text(
              initial,
              style: AppTextStyles.label.copyWith(color: AppColors.primary),
            ),
          ),
          const SizedBox(width: AppSpacing.m),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  payment.merchant,
                  style: AppTextStyles.bodyStrong,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                Text(
                  '$what · ${payment.seq}/${payment.count}'
                  '${payment.isEstimated ? ' · tahmini' : ''}',
                  style: AppTextStyles.bodyS.copyWith(
                    color: AppColors.textMuted,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.s),
          Text(
            formatMoneyTl(payment.amountMinor),
            style: AppTextStyles.bodyStrong,
          ),
        ],
      ),
    );
  }
}

/// "Önümüzdeki aylar": six bars, the chosen month dark, the others light.
class _NextMonths extends StatelessWidget {
  const _NextMonths({required this.months});

  final List<MonthTotal> months;

  @override
  Widget build(BuildContext context) {
    final largest = months.fold<int>(
      0,
      (m, e) => e.totalMinor > m ? e.totalMinor : m,
    );
    return Container(
      padding: const EdgeInsets.only(top: AppSpacing.s),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Önümüzdeki aylar',
            style: AppTextStyles.label.copyWith(color: AppColors.textMuted),
          ),
          const SizedBox(height: AppSpacing.s),
          SizedBox(
            height: AppSizes.chartBarMaxHeight + AppSpacing.xs + AppSpacing.l,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                for (var i = 0; i < months.length; i++)
                  Column(
                    key: Key('home_chart_bar_$i'),
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      Tooltip(
                        message: formatMoneyTl(months[i].totalMinor),
                        child: Container(
                          width: AppSizes.chartBarWidth,
                          height: largest <= 0
                              ? 0
                              : AppSizes.chartBarMaxHeight *
                                    months[i].totalMinor /
                                    largest,
                          decoration: BoxDecoration(
                            color: i == 0
                                ? AppColors.primary
                                : AppColors.primarySoft,
                            borderRadius: BorderRadius.vertical(
                              top: Radius.circular(AppRadius.chartBar),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: AppSpacing.xs),
                      Text(
                        formatMonthShortTr(months[i].month),
                        style: AppTextStyles.caption.copyWith(
                          color: AppColors.textSubtle,
                        ),
                      ),
                    ],
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
