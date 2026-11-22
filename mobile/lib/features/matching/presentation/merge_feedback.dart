import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../transactions/data/transactions_api.dart';
import '../../transactions/data/transactions_providers.dart';
import '../data/matching_providers.dart';
import '../domain/match_models.dart';

/// The snackbar after an automatic merge: what happened, and "Geri al".
///
/// It outlives the screen that saved (the app goes back to the list right after), so it keeps
/// the [container] instead of a `ref`: undoing calls the API, then refreshes the list and the
/// open suggestions.
void showMergedSnackBar({
  required ScaffoldMessengerState messenger,
  required ProviderContainer container,
  required String message,
  required List<UndoableMerge> merges,
}) {
  messenger.showSnackBar(
    SnackBar(
      key: const Key('merged_snackbar'),
      content: Text(message),
      duration: const Duration(seconds: 10),
      action: SnackBarAction(
        label: 'Geri al',
        onPressed: () async {
          try {
            final api = container.read(transactionsApiProvider);
            for (final merge in merges) {
              await api.unmerge(merge.transactionId, merge.observationId);
            }
            container
              ..invalidate(purchaseListProvider)
              ..invalidate(pendingMatchesProvider);
            messenger.showSnackBar(
              const SnackBar(content: Text('Birleştirme geri alındı.')),
            );
          } on ApiError catch (error) {
            messenger.showSnackBar(SnackBar(content: Text(error.message)));
          }
        },
      ),
    ),
  );
}
