import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/utils/money_format.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../capture/presentation/review/review_widgets.dart' show CategoryDot;
import '../../home/presentation/home_widgets.dart';
import '../../transactions/domain/spending_category.dart';
import '../data/analytics_api.dart';
import '../data/analytics_providers.dart';
import '../domain/analytics_models.dart';

/// "Bütçeler": a monthly limit per category, measured on the spending view of this month (net
/// of refunds; installment payments do not count). From 80 % the bar turns orange, from 100 %
/// red; the home screen lists those under "Dikkat gerektirenler". No Figma frame: tokens only.
class BudgetsScreen extends ConsumerWidget {
  const BudgetsScreen({super.key});

  Future<void> _edit(
    BuildContext context,
    WidgetRef ref,
    SpendingCategory category,
    BudgetUsage? current,
  ) async {
    final result = await showDialog<_EditResult>(
      context: context,
      builder: (_) => _LimitDialog(category: category, current: current),
    );
    if (result == null || !context.mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    final api = ref.read(analyticsApiProvider);
    try {
      if (result.delete) {
        await api.deleteBudget(category);
      } else {
        await api.putBudget(category, result.limitMinor!);
      }
      ref
        ..invalidate(budgetListProvider)
        ..invalidate(homeDataProvider);
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            result.delete
                ? '${category.label} bütçesi silindi.'
                : '${category.label} bütçesi kaydedildi.',
          ),
        ),
      );
    } on ApiError catch (error) {
      messenger.showSnackBar(SnackBar(content: Text(error.message)));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final budgets = ref.watch(budgetListProvider);
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(title: const Text('Bütçeler')),
      body: SafeArea(
        child: budgets.when(
          loading: () => const LoadingView(),
          error: (error, _) => ErrorView(
            message: error is ApiError
                ? error.message
                : 'Bütçeler yüklenemedi.',
            onRetry: () => ref.invalidate(budgetListProvider),
          ),
          data: (items) {
            final byCategory = {for (final b in items) b.category: b};
            return ListView(
              padding: const EdgeInsets.all(AppSpacing.screenH),
              children: [
                Text(
                  'Bu ayın harcaması kategori limitleriyle karşılaştırılır. '
                  'Taksit ödemeleri sayılmaz.',
                  style: AppTextStyles.bodyS.copyWith(
                    color: AppColors.textMuted,
                  ),
                ),
                const SizedBox(height: AppSpacing.m),
                HomeCard(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.l,
                    vertical: AppSpacing.xxs,
                  ),
                  child: Column(
                    children: [
                      for (var i = 0; i < SpendingCategory.values.length; i++)
                        _BudgetTile(
                          category: SpendingCategory.values[i],
                          budget: byCategory[SpendingCategory.values[i]],
                          first: i == 0,
                          onTap: () => _edit(
                            context,
                            ref,
                            SpendingCategory.values[i],
                            byCategory[SpendingCategory.values[i]],
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _BudgetTile extends StatelessWidget {
  const _BudgetTile({
    required this.category,
    required this.budget,
    required this.first,
    required this.onTap,
  });

  final SpendingCategory category;
  final BudgetUsage? budget;
  final bool first;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final b = budget;
    final color = switch (b?.state) {
      BudgetState.over => AppColors.danger,
      BudgetState.warning => AppColors.warning,
      _ => AppColors.primary,
    };
    final soft = switch (b?.state) {
      BudgetState.over => AppColors.dangerSoft,
      BudgetState.warning => AppColors.warningSoft,
      _ => AppColors.primarySoft,
    };
    return InkWell(
      key: Key('budget_${category.key}'),
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
                CategoryDot(color: category.color),
                const SizedBox(width: AppSpacing.s),
                Expanded(
                  child: Text(category.label, style: AppTextStyles.body),
                ),
                Text(
                  b == null
                      ? 'Bütçe ekle'
                      : '%${b.pct} · ${formatMoneyTl(b.spentMinor)} / '
                            '${formatMoneyTl(b.limitMinor)}',
                  style: b == null
                      ? AppTextStyles.label.copyWith(color: AppColors.primary)
                      : AppTextStyles.bodyS.copyWith(color: color),
                ),
              ],
            ),
            if (b != null) ...[
              const SizedBox(height: AppSpacing.s),
              ProgressTrack(
                fraction: b.pct / 100,
                color: color,
                background: soft,
                height: AppSizes.budgetTrack,
                radius: AppRadius.xs,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _EditResult {
  const _EditResult.save(this.limitMinor) : delete = false;
  const _EditResult.delete() : limitMinor = null, delete = true;

  final int? limitMinor;
  final bool delete;
}

class _LimitDialog extends StatefulWidget {
  const _LimitDialog({required this.category, required this.current});

  final SpendingCategory category;
  final BudgetUsage? current;

  @override
  State<_LimitDialog> createState() => _LimitDialogState();
}

class _LimitDialogState extends State<_LimitDialog> {
  late final _controller = TextEditingController(
    text: widget.current == null
        ? ''
        : formatMoneyMinor(widget.current!.limitMinor),
  );
  int? _value;

  @override
  void initState() {
    super.initState();
    _value = parseMoneyToMinor(_controller.text);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final valid = _value != null && _value! > 0;
    return AlertDialog(
      title: Text('${widget.category.label} bütçesi'),
      content: TextField(
        key: const Key('budget_limit_field'),
        controller: _controller,
        autofocus: true,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: const InputDecoration(
          labelText: 'Aylık limit',
          suffixText: 'TL',
        ),
        onChanged: (text) => setState(() => _value = parseMoneyToMinor(text)),
      ),
      actions: [
        if (widget.current != null)
          TextButton(
            key: const Key('budget_delete'),
            onPressed: () =>
                Navigator.of(context).pop(const _EditResult.delete()),
            child: const Text('Sil'),
          ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Vazgeç'),
        ),
        TextButton(
          key: const Key('budget_save'),
          onPressed: valid
              ? () => Navigator.of(context).pop(_EditResult.save(_value!))
              : null,
          child: const Text('Kaydet'),
        ),
      ],
    );
  }
}
