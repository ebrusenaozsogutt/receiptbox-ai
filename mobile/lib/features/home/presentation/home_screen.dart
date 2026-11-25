import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/utils/date_format.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../analytics/data/analytics_providers.dart';
import '../../analytics/domain/analytics_models.dart';
import 'home_widgets.dart';

/// "Ana Sayfa" (Figma "01 · Ana Sayfa"). The order is fixed (spec 11.1): spending at the top,
/// then what needs attention, then the installment payments due at the bottom. Every number
/// comes from the backend's SQL; payments are never part of the spending.
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  final _attentionKey = GlobalKey();

  Future<void> _pickMonth() async {
    final current = ref.read(homeMonthProvider);
    final now = ref.read(analyticsClockProvider)();
    final picked = await showModalBottomSheet<DateTime>(
      context: context,
      useRootNavigator: true,
      builder: (_) => MonthPickerSheet(
        selected: current,
        latest: DateTime(now.year, now.month + 12),
      ),
    );
    if (picked != null) ref.read(homeMonthProvider.notifier).set(picked);
  }

  /// The bell: notifications arrive with P13; until then it shows what needs attention.
  void _showAttention() {
    final target = _attentionKey.currentContext;
    if (target != null) {
      Scrollable.ensureVisible(
        target,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final month = ref.watch(homeMonthProvider);
    final home = ref.watch(homeDataProvider);
    final today = ref.watch(analyticsClockProvider)();
    return SafeArea(
      child: RefreshIndicator(
        onRefresh: () => ref.refresh(homeDataProvider.future),
        child: ListView(
          key: const Key('home_list'),
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.screenH,
            AppSpacing.m,
            AppSpacing.screenH,
            AppSpacing.xxl,
          ),
          children: [
            HomeHeader(
              month: month,
              onPickMonth: _pickMonth,
              onBell: _showAttention,
            ),
            const SizedBox(height: AppSpacing.xl),
            ...home.when(
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
                      : 'Ana sayfa yüklenemedi.',
                  onRetry: () => ref.invalidate(homeDataProvider),
                ),
              ],
              data: (data) => _sections(data, today),
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _sections(HomeData data, DateTime today) => [
    SpendingHero(spending: data.spending, today: today),
    const SizedBox(height: AppSpacing.xl),
    CategoryBreakdown(
      categories: data.spending.byCategory,
      onAll: () => context.push('/analytics'),
    ),
    const SizedBox(height: AppSpacing.xl),
    KeyedSubtree(
      key: _attentionKey,
      child: AttentionSection(
        items: data.attention,
        onBudget: () => context.push('/budgets'),
        onProduct: (id) => context.push('/products/$id'),
      ),
    ),
    const SizedBox(height: AppSpacing.xl),
    PaymentsDueCard(
      data: data,
      today: today,
      onPayment: (payment) =>
          context.push('/transactions/${payment.transactionId}'),
    ),
  ];
}

/// Pick a month: a year with its twelve months (no month after [latest]).
class MonthPickerSheet extends StatefulWidget {
  const MonthPickerSheet({
    super.key,
    required this.selected,
    required this.latest,
  });

  final DateTime selected;
  final DateTime latest;

  @override
  State<MonthPickerSheet> createState() => _MonthPickerSheetState();
}

class _MonthPickerSheetState extends State<MonthPickerSheet> {
  late int _year = widget.selected.year;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.screenH),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                IconButton(
                  key: const Key('month_previous_year'),
                  tooltip: 'Önceki yıl',
                  icon: const Icon(Icons.chevron_left),
                  onPressed: () => setState(() => _year--),
                ),
                Expanded(
                  child: Text(
                    '$_year',
                    textAlign: TextAlign.center,
                    style: AppTextStyles.titleM,
                  ),
                ),
                IconButton(
                  key: const Key('month_next_year'),
                  tooltip: 'Sonraki yıl',
                  icon: const Icon(Icons.chevron_right),
                  onPressed: _year < widget.latest.year
                      ? () => setState(() => _year++)
                      : null,
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.m),
            Wrap(
              spacing: AppSpacing.s,
              runSpacing: AppSpacing.s,
              alignment: WrapAlignment.center,
              children: [
                for (var m = 1; m <= 12; m++)
                  _MonthChip(
                    month: DateTime(_year, m),
                    selected: isSameMonth(DateTime(_year, m), widget.selected),
                    enabled: !DateTime(_year, m).isAfter(widget.latest),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _MonthChip extends StatelessWidget {
  const _MonthChip({
    required this.month,
    required this.selected,
    required this.enabled,
  });

  final DateTime month;
  final bool selected;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return ChoiceChip(
      key: Key('month_${monthToApi(month)}'),
      label: Text(formatMonthShortTr(month)),
      selected: selected,
      selectedColor: AppColors.primarySoft,
      labelStyle: AppTextStyles.label.copyWith(
        color: selected ? AppColors.primary : AppColors.text,
      ),
      onSelected: enabled ? (_) => Navigator.of(context).pop(month) : null,
    );
  }
}
