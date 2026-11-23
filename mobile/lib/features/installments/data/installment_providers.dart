import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../transactions/data/transactions_api.dart';
import '../domain/installment_models.dart';

part 'installment_providers.g.dart';

/// The payment schedule: this month and the next eleven. Invalidate it after saving, linking a
/// bank row or changing a plan.
@riverpod
Future<InstallmentSchedule> installmentSchedule(Ref ref) {
  final now = DateTime.now();
  final from = DateTime(now.year, now.month);
  return ref
      .watch(transactionsApiProvider)
      .schedule(from: from, to: DateTime(from.year, from.month + 11));
}
