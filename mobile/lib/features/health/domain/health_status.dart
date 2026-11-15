/// Result of `GET /api/v1/health`.
class HealthStatus {
  const HealthStatus({required this.status, required this.db});

  final String status;
  final String db;

  /// True only when both the API and its database are fine.
  bool get isHealthy => status == 'ok' && db == 'ok';

  factory HealthStatus.fromJson(Map<String, dynamic> json) {
    return HealthStatus(
      status: json['status'] as String,
      db: json['db'] as String,
    );
  }
}
