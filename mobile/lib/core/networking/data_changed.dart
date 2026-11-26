import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'data_changed.g.dart';

/// Raised after every successful request that changed something on the backend (POST, PUT,
/// PATCH, DELETE). The reminders feature listens to it: any change can move a deadline
/// (a product, a warranty, a plan, a refund, a deleted purchase), so the notifications are
/// rescheduled. (A signal provider keeps core/ from depending on features/.)
@Riverpod(keepAlive: true)
class DataChangedSignal extends _$DataChangedSignal {
  @override
  int build() => 0;

  void signal() => state++;
}

/// Calls [onChanged] after a successful write; reads are ignored.
class DataChangedInterceptor extends Interceptor {
  DataChangedInterceptor(this.onChanged);

  final void Function() onChanged;

  static const _writes = {'POST', 'PUT', 'PATCH', 'DELETE'};

  @override
  void onResponse(
    Response<dynamic> response,
    ResponseInterceptorHandler handler,
  ) {
    final method = response.requestOptions.method.toUpperCase();
    final status = response.statusCode ?? 0;
    if (_writes.contains(method) && status >= 200 && status < 300) {
      onChanged();
    }
    handler.next(response);
  }
}
