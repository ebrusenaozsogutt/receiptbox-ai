import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/networking/dio_provider.dart';
import '../domain/reminder_models.dart';

part 'reminders_api.g.dart';

/// Backend P13: the reminders to schedule as local notifications.
abstract interface class RemindersApi {
  /// Not dismissed, from one day ago up to [days] ahead, soonest first.
  Future<List<Reminder>> upcoming({int days = 60});
}

class DioRemindersApi implements RemindersApi {
  DioRemindersApi(this._dio);

  final Dio _dio;

  @override
  Future<List<Reminder>> upcoming({int days = 60}) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        '/reminders/upcoming',
        queryParameters: {'days': days},
      );
      return [
        for (final item in response.data!['items'] as List<dynamic>)
          ?Reminder.fromJson(item as Map<String, dynamic>),
      ];
    } on Object catch (error) {
      throw apiErrorFrom(error);
    }
  }
}

@Riverpod(keepAlive: true)
RemindersApi remindersApi(Ref ref) => DioRemindersApi(ref.watch(dioProvider));
