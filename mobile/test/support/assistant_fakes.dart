import 'dart:async';

import 'package:receiptbox/core/networking/api_error.dart';
import 'package:receiptbox/features/assistant/data/assistant_api.dart';
import 'package:receiptbox/features/assistant/domain/assistant_models.dart';

/// The backend's assistant, scripted per test: queue replies (or errors) in order.
class FakeAssistantApi implements AssistantApi {
  final replies = <Object>[];
  final questions = <String>[];
  final histories = <List<ChatExchange>>[];
  int clearCalls = 0;
  ApiError? clearError;

  /// While set, a question waits for it (to see the typing indicator).
  Completer<void>? gate;

  void reply(
    String answer, {
    List<AssistantAction> actions = const [],
    List<String> tools = const [],
  }) => replies.add(
    AssistantReply(answer: answer, actions: actions, tools: tools),
  );

  void fail(String code) => replies.add(
    ApiError(code: code, message: messageForCode(code), statusCode: 503),
  );

  @override
  Future<AssistantReply> chat({
    required String message,
    required List<ChatExchange> history,
  }) async {
    questions.add(message);
    histories.add(List.of(history));
    if (gate != null) await gate!.future;
    final next = replies.isEmpty
        ? const AssistantReply(answer: 'Tamam.')
        : replies.removeAt(0);
    if (next is ApiError) throw next;
    return next as AssistantReply;
  }

  @override
  Future<void> clearHistory() async {
    clearCalls++;
    if (clearError != null) throw clearError!;
  }
}
