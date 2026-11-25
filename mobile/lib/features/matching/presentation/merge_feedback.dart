import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../transactions/data/transactions_api.dart';
import '../../transactions/data/transactions_providers.dart';
import '../data/matching_providers.dart';
import '../domain/match_models.dart';

/// How long "Geri al" stays on screen.
const mergedSnackBarDuration = Duration(seconds: 6);

/// The "Geri al" snackbar on screen, if any (one at a time: a new one replaces it).
ScaffoldFeatureController<SnackBar, SnackBarClosedReason>? _activeMerged;

/// Hides the "Geri al" snackbar, if one is showing. Called when the user leaves the screen it
/// was shown on (a new page, another tab), so it never covers the next screen's buttons.
void dismissMergedSnackBar() {
  final active = _activeMerged;
  _activeMerged = null;
  active?.close();
}

/// Hides the "Geri al" snackbar when a new page is opened on top of another one. Dialogs and
/// bottom sheets (popup routes) do not count; going back (pop) does not either, because every
/// save shows the snackbar and then goes back to the list; neither does the first page of a
/// navigator that is just being built (a tab opened for the first time). The snackbar is closed
/// after the frame, because a push can be reported while the widgets are being built.
class MergedSnackBarDismisser extends NavigatorObserver {
  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    if (route is! PageRoute || previousRoute == null || _activeMerged == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) => dismissMergedSnackBar());
  }
}

/// The snackbar after an automatic merge: what happened, and "Geri al".
///
/// It outlives the screen that saved (the app goes back to the list right after), so it keeps
/// the [container] instead of a `ref`: undoing calls the API, then refreshes the list and the
/// open suggestions. It closes after [mergedSnackBarDuration] (a snackbar with an action would
/// otherwise stay until it is swiped away) or when the user opens another page or tab.
void showMergedSnackBar({
  required ScaffoldMessengerState messenger,
  required ProviderContainer container,
  required String message,
  required List<UndoableMerge> merges,
}) {
  final controller = messenger.showSnackBar(
    SnackBar(
      key: const Key('merged_snackbar'),
      content: Text(message),
      duration: mergedSnackBarDuration,
      persist: false,
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
  _activeMerged = controller;
  controller.closed.then((_) {
    if (identical(_activeMerged, controller)) _activeMerged = null;
  });
}
