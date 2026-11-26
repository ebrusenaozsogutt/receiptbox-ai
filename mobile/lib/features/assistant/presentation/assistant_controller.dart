import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../core/networking/api_error.dart';
import '../../auth/domain/auth_state.dart';
import '../../auth/presentation/auth_controller.dart';
import '../data/assistant_api.dart';
import '../domain/assistant_models.dart';

part 'assistant_controller.g.dart';

/// The chat on the Asistan tab. It lives in memory only (it survives switching tabs, not a
/// restart, and is dropped on sign-out); the backend keeps the turns until "Geçmişi temizle".
@Riverpod(keepAlive: true)
class AssistantChat extends _$AssistantChat {
  @override
  List<ChatExchange> build() {
    ref.listen<AuthState>(authProvider, (previous, next) {
      if (next.status != AuthStatus.authenticated) state = const [];
    });
    return const [];
  }

  bool get busy => state.any((exchange) => exchange.pending);

  /// Asks [text]; ignored while an answer is still coming.
  Future<void> ask(String text) async {
    final question = text.trim();
    if (question.isEmpty || busy) return;
    final history = [...state];
    state = [...state, ChatExchange(question: question)];
    await _answer(state.length - 1, history);
  }

  /// Asks the last question again after an error.
  Future<void> retry() async {
    if (state.isEmpty || state.last.error == null || busy) return;
    final index = state.length - 1;
    final history = state.sublist(0, index);
    _replace(index, ChatExchange(question: state[index].question));
    await _answer(index, history);
  }

  /// Deletes the history on the server, then on the screen. False when the server failed.
  Future<bool> clear() async {
    try {
      await ref.read(assistantApiProvider).clearHistory();
    } on ApiError {
      return false;
    }
    state = const [];
    return true;
  }

  Future<void> _answer(int index, List<ChatExchange> history) async {
    final question = state[index].question;
    ChatExchange result;
    try {
      final reply = await ref
          .read(assistantApiProvider)
          .chat(message: question, history: history);
      result = ChatExchange(question: question, reply: reply);
    } on ApiError catch (error) {
      result = ChatExchange(question: question, error: _message(error));
    }
    // The chat may have been cleared (sign-out) while waiting.
    if (index < state.length && state[index].question == question) {
      _replace(index, result);
    }
  }

  void _replace(int index, ChatExchange exchange) {
    state = [...state]..[index] = exchange;
  }

  static String _message(ApiError error) {
    if (error.code == 'AI_CONSENT_REQUIRED') {
      return "Asistan için yapay zekâ izni gerekiyor. Ayarlar'dan açabilirsin.";
    }
    return error.message;
  }
}
