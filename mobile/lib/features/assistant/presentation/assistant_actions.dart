import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../transactions/data/transactions_providers.dart';
import '../../transactions/domain/spending_category.dart';
import '../domain/assistant_models.dart';

/// Opens the screen an answer's button points at, so the user can check the numbers there.
void openAssistantAction(
  BuildContext context,
  WidgetRef ref,
  AssistantAction action,
) {
  final params = action.params;
  switch (action.type) {
    case AssistantActionType.openTransactions:
      ref
          .read(purchaseFilterControllerProvider.notifier)
          .set(
            PurchaseFilter(
              from: DateTime.tryParse(params['from'] ?? ''),
              to: DateTime.tryParse(params['to'] ?? ''),
              category: SpendingCategory.fromKey(params['category']),
              search: params['q'] ?? '',
            ),
          );
      context.go('/transactions');
    case AssistantActionType.openProduct:
      final id = params['id'];
      if (id != null) context.push('/products/$id');
    case AssistantActionType.openDocument:
      final id = params['id'];
      if (id != null) {
        context.push('/documents/$id/view?pdf=${params['pdf'] == 'true'}');
      }
    case AssistantActionType.openInstallments:
      final month = params['month'];
      context.push(
        month == null ? '/installments' : '/installments?month=$month',
      );
  }
}

IconData assistantActionIcon(AssistantActionType type) => switch (type) {
  AssistantActionType.openTransactions => Icons.receipt_long_outlined,
  AssistantActionType.openProduct => Icons.inventory_2_outlined,
  AssistantActionType.openDocument => Icons.description_outlined,
  AssistantActionType.openInstallments => Icons.calendar_month_outlined,
};
