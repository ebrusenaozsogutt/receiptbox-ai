import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/networking/dio_provider.dart';
import '../../transactions/domain/purchase_models.dart' show dateToApi;
import '../../transactions/domain/spending_category.dart';
import '../domain/analytics_models.dart';

part 'analytics_api.g.dart';

/// The analytics and budget endpoints (P11). Every number comes from the backend's SQL.
abstract interface class AnalyticsApi {
  /// The home screen of [month] (spending, attention, payments due).
  Future<HomeData> home(DateTime month);

  /// Net spending of a period grouped by "category", "merchant", "month" or "week".
  Future<SpendingGroups> spending({
    required DateTime from,
    required DateTime to,
    required String groupBy,
    int? limit,
  });

  /// Period a compared with period b (delta = a - b).
  Future<Comparison> compare({
    required DateTime aFrom,
    required DateTime aTo,
    required DateTime bFrom,
    required DateTime bTo,
  });

  /// One or two sentences from the AI about the comparison, or null (no consent, AI failed).
  Future<String?> commentary({
    required DateTime aFrom,
    required DateTime aTo,
    required DateTime bFrom,
    required DateTime bTo,
  });

  Future<YearSummary> year(int year);

  Future<List<BudgetUsage>> budgets({DateTime? month});

  /// Set or change a category's monthly limit; answers this month's budgets.
  Future<List<BudgetUsage>> putBudget(
    SpendingCategory category,
    int limitMinor,
  );

  Future<void> deleteBudget(SpendingCategory category);
}

class DioAnalyticsApi implements AnalyticsApi {
  const DioAnalyticsApi(this._dio);

  final Dio _dio;

  Future<T> _guard<T>(Future<T> Function() call) async {
    try {
      return await call();
    } on Object catch (error) {
      throw apiErrorFrom(error);
    }
  }

  Map<String, String> _periods(
    DateTime aFrom,
    DateTime aTo,
    DateTime bFrom,
    DateTime bTo,
  ) => {
    'a_from': dateToApi(aFrom),
    'a_to': dateToApi(aTo),
    'b_from': dateToApi(bFrom),
    'b_to': dateToApi(bTo),
  };

  List<BudgetUsage> _budgetList(Map<String, dynamic> data) => [
    for (final b in data['budgets'] as List<dynamic>)
      BudgetUsage.fromJson(b as Map<String, dynamic>),
  ];

  @override
  Future<HomeData> home(DateTime month) => _guard(() async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/analytics/home',
      queryParameters: {'month': monthToApi(month)},
    );
    return HomeData.fromJson(response.data!);
  });

  @override
  Future<SpendingGroups> spending({
    required DateTime from,
    required DateTime to,
    required String groupBy,
    int? limit,
  }) => _guard(() async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/analytics/spending',
      queryParameters: {
        'from': dateToApi(from),
        'to': dateToApi(to),
        'group_by': groupBy,
        'limit': ?limit,
      },
    );
    return SpendingGroups.fromJson(response.data!);
  });

  @override
  Future<Comparison> compare({
    required DateTime aFrom,
    required DateTime aTo,
    required DateTime bFrom,
    required DateTime bTo,
  }) => _guard(() async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/analytics/compare',
      queryParameters: _periods(aFrom, aTo, bFrom, bTo),
    );
    return Comparison.fromJson(response.data!);
  });

  @override
  Future<String?> commentary({
    required DateTime aFrom,
    required DateTime aTo,
    required DateTime bFrom,
    required DateTime bTo,
  }) => _guard(() async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/analytics/compare/commentary',
      queryParameters: _periods(aFrom, aTo, bFrom, bTo),
    );
    return response.data!['commentary'] as String?;
  });

  @override
  Future<YearSummary> year(int year) => _guard(() async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/analytics/year',
      queryParameters: {'year': year},
    );
    return YearSummary.fromJson(response.data!);
  });

  @override
  Future<List<BudgetUsage>> budgets({DateTime? month}) => _guard(() async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/budgets',
      queryParameters: {if (month != null) 'month': monthToApi(month)},
    );
    return _budgetList(response.data!);
  });

  @override
  Future<List<BudgetUsage>> putBudget(
    SpendingCategory category,
    int limitMinor,
  ) => _guard(() async {
    final response = await _dio.put<Map<String, dynamic>>(
      '/budgets',
      data: {'category_key': category.key, 'monthly_limit_minor': limitMinor},
    );
    return _budgetList(response.data!);
  });

  @override
  Future<void> deleteBudget(SpendingCategory category) => _guard(() async {
    await _dio.delete<void>('/budgets/${category.key}');
  });
}

@Riverpod(keepAlive: true)
AnalyticsApi analyticsApi(Ref ref) => DioAnalyticsApi(ref.watch(dioProvider));
