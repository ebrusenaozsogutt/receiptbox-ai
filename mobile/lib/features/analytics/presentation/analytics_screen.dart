import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/utils/date_format.dart';
import '../../../core/utils/money_format.dart';
import '../../../core/widgets/app_segmented.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../capture/presentation/review/review_widgets.dart' show CategoryDot;
import '../../home/presentation/home_widgets.dart';
import '../../transactions/domain/spending_category.dart';
import '../data/analytics_providers.dart';
import '../domain/analytics_models.dart';

/// "Analiz": spending of this week, month or year by category and by merchant, compared with
/// the period before (plus an optional AI sentence written from those numbers only). No Figma
/// frame: built from the tokens and the home screen's cards.
class AnalyticsScreen extends ConsumerWidget {
  const AnalyticsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final period = ref.watch(analyticsPeriodControllerProvider);
    final view = ref.watch(analyticsViewProvider);
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        title: const Text('Analiz'),
        actions: [
          TextButton(
            key: const Key('open_budgets'),
            onPressed: () => context.push('/budgets'),
            child: const Text('Bütçeler'),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(AppSpacing.screenH),
          children: [
            AppSegmented<AnalyticsPeriod>(
              key: const Key('analytics_period'),
              segments: [
                for (final p in AnalyticsPeriod.values) Segment(p, p.label),
              ],
              selected: period,
              onChanged: ref
                  .read(analyticsPeriodControllerProvider.notifier)
                  .set,
            ),
            const SizedBox(height: AppSpacing.l),
            ...view.when(
              loading: () => const [
                SizedBox(
                  height: AppSizes.resultTextMaxHeight,
                  child: LoadingView(),
                ),
              ],
              error: (error, _) => [
                ErrorView(
                  message: error is ApiError
                      ? error.message
                      : 'Analiz yüklenemedi.',
                  onRetry: () => ref.invalidate(analyticsViewProvider),
                ),
              ],
              data: (data) => _body(data),
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _body(AnalyticsView data) => [
    _TotalCard(data: data),
    const SizedBox(height: AppSpacing.m),
    _ComparisonCard(data: data),
    const SizedBox(height: AppSpacing.m),
    _GroupCard(
      key: const Key('analytics_categories'),
      title: 'Kategoriler',
      empty: 'Bu dönemde harcama yok.',
      rows: [
        for (final g in data.byCategory.groups)
          _BarRow(
            label: SpendingCategory.fromKey(g.key)?.label ?? g.label,
            totalMinor: g.totalMinor,
            color: (SpendingCategory.fromKey(g.key) ?? SpendingCategory.other)
                .color,
          ),
      ],
    ),
    const SizedBox(height: AppSpacing.m),
    _GroupCard(
      key: const Key('analytics_merchants'),
      title: 'En çok harcanan yerler',
      empty: 'Bu dönemde harcama yok.',
      rows: [
        for (final g in data.topMerchants.groups)
          _BarRow(
            label: g.label,
            totalMinor: g.totalMinor,
            color: AppColors.primary,
          ),
      ],
    ),
    if (data.period == AnalyticsPeriod.year) ...[
      const SizedBox(height: AppSpacing.m),
      _GroupCard(
        key: const Key('analytics_months'),
        title: 'Aylar',
        empty: '',
        rows: [
          for (final m in data.byMonth)
            _BarRow(
              label: formatMonthTr(m.month),
              totalMinor: m.totalMinor,
              color: AppColors.primary,
            ),
        ],
      ),
    ],
  ];
}

String _periodLabel(AnalyticsView data) => switch (data.period) {
  AnalyticsPeriod.week =>
    '${formatDateTr(data.from)} - ${formatDateTr(data.to)}',
  AnalyticsPeriod.month => formatMonthTr(data.from),
  AnalyticsPeriod.year => '${data.from.year}',
};

class _TotalCard extends StatelessWidget {
  const _TotalCard({required this.data});

  final AnalyticsView data;

  @override
  Widget build(BuildContext context) {
    return HomeCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            _periodLabel(data),
            style: AppTextStyles.label.copyWith(color: AppColors.textMuted),
          ),
          const SizedBox(height: AppSpacing.xxs),
          Text(
            formatMoneyTl(data.byCategory.totalMinor),
            key: const Key('analytics_total'),
            style: AppTextStyles.display,
          ),
          Text(
            'İadeler düşüldü; taksit ödemeleri harcamaya eklenmez.',
            style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
          ),
        ],
      ),
    );
  }
}

/// "Önceki döneme göre": the change and the three categories that changed most, and the AI's
/// sentence when there is one.
class _ComparisonCard extends ConsumerWidget {
  const _ComparisonCard({required this.data});

  final AnalyticsView data;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final comparison = data.comparison;
    final commentary = ref.watch(comparisonCommentaryProvider).value;
    final change = comparison.deltaMinor;
    final pct = comparison.deltaPct;
    final color = change > 0
        ? AppColors.danger
        : change < 0
        ? AppColors.success
        : AppColors.textMuted;
    return HomeCard(
      key: const Key('analytics_comparison'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Önceki döneme göre', style: AppTextStyles.titleS),
          const SizedBox(height: AppSpacing.xs),
          Text(
            '${change > 0 ? '+' : ''}${formatMoneyTl(change)}'
            '${pct == null ? '' : ' (${change < 0 ? '-' : ''}${percentTr(pct)})'}',
            key: const Key('analytics_delta'),
            style: AppTextStyles.titleM.copyWith(color: color),
          ),
          Text(
            'Önceki dönem: ${formatMoneyTl(comparison.bTotalMinor)}',
            style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
          ),
          for (final c in comparison.topCategories) ...[
            const SizedBox(height: AppSpacing.s),
            Row(
              key: Key('analytics_change_${c.category.key}'),
              children: [
                CategoryDot(color: c.category.color),
                const SizedBox(width: AppSpacing.s),
                Expanded(
                  child: Text(c.category.label, style: AppTextStyles.body),
                ),
                Text(
                  '${c.deltaMinor > 0 ? '+' : ''}${formatMoneyTl(c.deltaMinor)}',
                  style: AppTextStyles.bodyStrong,
                ),
              ],
            ),
          ],
          if (commentary != null && commentary.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.m),
            Container(
              key: const Key('analytics_commentary'),
              width: double.infinity,
              padding: const EdgeInsets.all(AppSpacing.m),
              decoration: BoxDecoration(
                color: AppColors.primarySoft,
                borderRadius: AppRadius.control,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'AI YORUMU',
                    style: AppTextStyles.overline.copyWith(
                      color: AppColors.primary,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.xxs),
                  Text(commentary, style: AppTextStyles.body),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _BarRow {
  const _BarRow({
    required this.label,
    required this.totalMinor,
    required this.color,
  });

  final String label;
  final int totalMinor;
  final Color color;
}

class _GroupCard extends StatelessWidget {
  const _GroupCard({
    super.key,
    required this.title,
    required this.rows,
    required this.empty,
  });

  final String title;
  final List<_BarRow> rows;
  final String empty;

  @override
  Widget build(BuildContext context) {
    final largest = rows.fold<int>(
      0,
      (m, r) => r.totalMinor > m ? r.totalMinor : m,
    );
    return HomeCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: AppTextStyles.titleM),
          if (rows.isEmpty) ...[
            const SizedBox(height: AppSpacing.s),
            Text(
              empty,
              style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
            ),
          ],
          for (final row in rows) ...[
            const SizedBox(height: AppSpacing.m),
            Row(
              children: [
                Expanded(
                  child: Text(
                    row.label,
                    style: AppTextStyles.body,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                Text(
                  formatMoneyTl(row.totalMinor),
                  style: AppTextStyles.bodyStrong,
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.xs),
            ProgressTrack(
              fraction: largest <= 0 ? 0 : row.totalMinor / largest,
              color: row.color,
              background: AppColors.surfaceAlt,
              height: AppSizes.categoryTrack,
              radius: AppRadius.track,
            ),
          ],
        ],
      ),
    );
  }
}
