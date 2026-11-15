/// Build-time configuration.
///
/// The backend URL is passed with `--dart-define`, for example:
///   flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
///
/// 10.0.2.2 is how the Android emulator reaches the host computer's localhost.
/// For a real phone over USB, use `adb reverse tcp:8000 tcp:8000` and
/// `--dart-define=API_BASE_URL=http://localhost:8000`.
class AppConfig {
  const AppConfig._();

  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static const String apiPrefix = '/api/v1';
}
