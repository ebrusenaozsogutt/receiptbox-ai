import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../transactions/data/transactions_api.dart';
import '../domain/match_models.dart';

part 'matching_providers.g.dart';

/// The suggestions that wait for the user's answer ("N eşleşme önerisi bekliyor").
/// Invalidate it after saving, answering or undoing something.
@riverpod
Future<List<MatchSuggestion>> pendingMatches(Ref ref) =>
    ref.watch(transactionsApiProvider).pendingMatches();
