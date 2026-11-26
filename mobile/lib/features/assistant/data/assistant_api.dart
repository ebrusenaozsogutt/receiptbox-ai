import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/networking/data_changed.dart';
import '../../../core/networking/dio_provider.dart';
import '../domain/assistant_models.dart';

part 'assistant_api.g.dart';

/// At most this many earlier turns go with a question (the backend's limit).
const assistantHistoryTurns = 6;

/// Backend P14: the AI assistant.
abstract interface class AssistantApi {
  /// Asks [message]; [history] holds the earlier answered questions, oldest first.
  Future<AssistantReply> chat({
    required String message,
    required List<ChatExchange> history,
  });

  /// Deletes the stored questions and answers on the server.
  Future<void> clearHistory();
}

class DioAssistantApi implements AssistantApi {
  DioAssistantApi(this._dio);

  final Dio _dio;

  /// The backend gives a turn at most 20 s; the phone waits a little longer than that.
  static const _answerTimeout = Duration(seconds: 30);

  @override
  Future<AssistantReply> chat({
    required String message,
    required List<ChatExchange> history,
  }) async {
    final answered = [
      for (final turn in history)
        if (turn.reply != null)
          {'question': turn.question, 'answer': turn.reply!.answer},
    ];
    final recent = answered.length > assistantHistoryTurns
        ? answered.sublist(answered.length - assistantHistoryTurns)
        : answered;
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/assistant/chat',
        data: {'message': message, 'history': recent},
        options: Options(
          receiveTimeout: _answerTimeout,
          // A question changes nothing the reminders depend on.
          extra: {DataChangedInterceptor.ignoreKey: true},
        ),
      );
      return AssistantReply.fromJson(response.data!);
    } on Object catch (error) {
      throw apiErrorFrom(error);
    }
  }

  @override
  Future<void> clearHistory() async {
    try {
      await _dio.delete<void>(
        '/assistant/history',
        options: Options(extra: {DataChangedInterceptor.ignoreKey: true}),
      );
    } on Object catch (error) {
      throw apiErrorFrom(error);
    }
  }
}

@Riverpod(keepAlive: true)
AssistantApi assistantApi(Ref ref) => DioAssistantApi(ref.watch(dioProvider));
