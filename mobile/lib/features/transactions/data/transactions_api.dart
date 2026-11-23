import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../../core/config/app_config.dart';
import '../../../core/networking/api_error.dart';
import '../../../core/networking/dio_provider.dart';
import '../../capture/domain/bank_models.dart';
import '../../installments/domain/installment_models.dart';
import '../../matching/domain/match_models.dart';
import '../domain/purchase_models.dart';
import '../domain/spending_category.dart';

part 'transactions_api.g.dart';

/// Transactions and the review queue (backend `/transactions`, `/observations`). Implementations
/// throw an [ApiError] with a Turkish message.
abstract interface class TransactionsApi {
  Future<PurchasePage> list({
    DateTime? from,
    DateTime? to,
    SpendingCategory? category,
    String? search,
    int limit = 30,
    int offset = 0,
  });
  Future<PurchaseDetail> detail(String id);

  /// A manual entry. Since P09 it may be attached to a purchase you already have, or ask first.
  Future<SaveResult> createManual(PurchaseInput input);
  Future<PurchaseDetail> update(String id, PurchaseInput input);
  Future<void> delete(String id);

  /// Save a reviewed receipt: a new purchase, or (P09) attached to the same purchase seen before,
  /// or a question first ([NeedsAnswer]).
  Future<SaveResult> confirm(String observationId, PurchaseInput input);
  Future<void> reject(String observationId);

  /// Save the selected bank rows as purchases (P08). [edits] holds what the user changed.
  Future<BatchResult> confirmBatch(
    List<String> ids,
    Map<String, BankRowEdit> edits,
  );

  // ---- matching (P09) -------------------------------------------------------------------------

  /// The suggestions waiting for an answer.
  Future<List<MatchSuggestion>> pendingMatches();

  /// "Birleştir".
  Future<PurchaseDetail> acceptMatch(String decisionId);

  /// "Ayrı kalsın": the waiting record becomes a purchase of its own.
  Future<PurchaseDetail> rejectMatch(String decisionId);

  /// "Ayır" / "Geri al": [observationId] leaves [transactionId] and becomes its own purchase.
  Future<UnmergeResult> unmerge(String transactionId, String observationId);

  // ---- installments (P10) ----------------------------------------------------------------------

  /// "Taksitli": [count] installments (2-36) for a purchase; replaces a plan that has no bank rows.
  Future<PurchaseDetail> putPlan(
    String transactionId, {
    required int count,
    DateTime? firstDueMonth,
    int? totalPayableMinor,
  });

  /// Cancel ([cancel] true) or reopen a plan.
  Future<PurchaseDetail> setPlanCancelled(
    String planId, {
    required bool cancel,
  });

  /// The payments of the active plans by month.
  Future<InstallmentSchedule> schedule({DateTime? from, DateTime? to});
}

/// Receipt images and invoice PDFs (backend `/documents`).
abstract interface class DocumentsApi {
  Future<DocumentInfo> upload(
    File file, {
    required String mimeType,
    required String type,
    required String transactionId,
  });

  /// A full address the app can show for 5 minutes (the token is inside it).
  Future<String> contentUrl(String documentId);

  /// The file itself: asks for a 5-minute access token, then downloads with it.
  Future<Uint8List> content(String documentId);
}

class DioTransactionsApi implements TransactionsApi {
  const DioTransactionsApi(this._dio);

  final Dio _dio;

  Future<T> _guard<T>(Future<T> Function() call) async {
    try {
      return await call();
    } on Object catch (error) {
      throw apiErrorFrom(error);
    }
  }

  @override
  Future<PurchasePage> list({
    DateTime? from,
    DateTime? to,
    SpendingCategory? category,
    String? search,
    int limit = 30,
    int offset = 0,
  }) => _guard(() async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/transactions',
      queryParameters: {
        if (from != null) 'from': dateToApi(from),
        if (to != null) 'to': dateToApi(to),
        if (category != null) 'category': category.key,
        if (search != null && search.trim().isNotEmpty) 'q': search.trim(),
        'limit': limit,
        'offset': offset,
      },
    );
    return PurchasePage.fromJson(response.data!);
  });

  @override
  Future<PurchaseDetail> detail(String id) => _guard(() async {
    final response = await _dio.get<Map<String, dynamic>>('/transactions/$id');
    return PurchaseDetail.fromJson(response.data!);
  });

  /// 201: saved (new or merged). 202: no purchase yet, the user is asked.
  SaveResult _saveResult(Response<Map<String, dynamic>> response) {
    final data = response.data!;
    if (response.statusCode == 202 || data['outcome'] == 'SUGGESTED') {
      return NeedsAnswer([
        for (final match in data['matches'] as List<dynamic>)
          MatchSuggestion.fromJson(match as Map<String, dynamic>),
      ]);
    }
    return Saved(PurchaseDetail.fromJson(data));
  }

  @override
  Future<SaveResult> createManual(PurchaseInput input) => _guard(() async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/transactions',
      data: input.toJson(withInstallments: true),
    );
    return _saveResult(response);
  });

  @override
  Future<PurchaseDetail> update(String id, PurchaseInput input) =>
      _guard(() async {
        final response = await _dio.patch<Map<String, dynamic>>(
          '/transactions/$id',
          data: input.toJson(),
        );
        return PurchaseDetail.fromJson(response.data!);
      });

  @override
  Future<void> delete(String id) =>
      _guard(() => _dio.delete<void>('/transactions/$id'));

  @override
  Future<SaveResult> confirm(String observationId, PurchaseInput input) =>
      _guard(() async {
        final response = await _dio.post<Map<String, dynamic>>(
          '/observations/$observationId/confirm',
          data: input.toJson(forConfirm: true),
        );
        return _saveResult(response);
      });

  @override
  Future<void> reject(String observationId) =>
      _guard(() => _dio.post<void>('/observations/$observationId/reject'));

  @override
  Future<BatchResult> confirmBatch(
    List<String> ids,
    Map<String, BankRowEdit> edits,
  ) => _guard(() async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/observations/confirm-batch',
      data: {
        'ids': ids,
        'edits': {
          for (final entry in edits.entries)
            if (ids.contains(entry.key))
              entry.key: {
                if (entry.value.merchant != null &&
                    entry.value.merchant!.trim().isNotEmpty)
                  'merchant_display': entry.value.merchant!.trim(),
                if (entry.value.date != null)
                  'date': dateToApi(entry.value.date!),
                if (entry.value.amountMinor != null)
                  'total_minor': entry.value.amountMinor,
                if (entry.value.category != null)
                  'category_key': entry.value.category!.key,
              },
        },
      },
    );
    return BatchResult.fromJson(response.data!);
  });

  @override
  Future<List<MatchSuggestion>> pendingMatches() => _guard(() async {
    final response = await _dio.get<List<dynamic>>(
      '/matches',
      queryParameters: {'decision': 'PENDING'},
    );
    return [
      for (final item in response.data!)
        MatchSuggestion.fromJson(item as Map<String, dynamic>),
    ];
  });

  @override
  Future<PurchaseDetail> acceptMatch(String decisionId) => _guard(() async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/matches/$decisionId/accept',
    );
    return PurchaseDetail.fromJson(response.data!);
  });

  @override
  Future<PurchaseDetail> rejectMatch(String decisionId) => _guard(() async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/matches/$decisionId/reject',
    );
    return PurchaseDetail.fromJson(response.data!);
  });

  @override
  Future<PurchaseDetail> putPlan(
    String transactionId, {
    required int count,
    DateTime? firstDueMonth,
    int? totalPayableMinor,
  }) => _guard(() async {
    final response = await _dio.put<Map<String, dynamic>>(
      '/transactions/$transactionId/installment-plan',
      data: {
        'count': count,
        if (firstDueMonth != null) 'first_due_month': dateToApi(firstDueMonth),
        'total_payable_minor': ?totalPayableMinor,
      },
    );
    return PurchaseDetail.fromJson(response.data!);
  });

  @override
  Future<PurchaseDetail> setPlanCancelled(
    String planId, {
    required bool cancel,
  }) => _guard(() async {
    final response = await _dio.patch<Map<String, dynamic>>(
      '/installment-plans/$planId',
      data: {'status': cancel ? 'CANCELLED' : 'ACTIVE'},
    );
    return PurchaseDetail.fromJson(response.data!);
  });

  @override
  Future<InstallmentSchedule> schedule({DateTime? from, DateTime? to}) =>
      _guard(() async {
        final response = await _dio.get<Map<String, dynamic>>(
          '/installments/schedule',
          queryParameters: {
            if (from != null) 'from': dateToApi(from),
            if (to != null) 'to': dateToApi(to),
          },
        );
        return InstallmentSchedule.fromJson(response.data!);
      });

  @override
  Future<UnmergeResult> unmerge(String transactionId, String observationId) =>
      _guard(() async {
        final response = await _dio.post<Map<String, dynamic>>(
          '/transactions/$transactionId/unmerge',
          data: {'observation_id': observationId},
        );
        return UnmergeResult.fromJson(response.data!);
      });
}

class DioDocumentsApi implements DocumentsApi {
  const DioDocumentsApi(this._dio);

  final Dio _dio;

  @override
  Future<DocumentInfo> upload(
    File file, {
    required String mimeType,
    required String type,
    required String transactionId,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/documents',
        data: FormData.fromMap({
          // A fixed, neutral file name: the real one is never sent.
          'file': await MultipartFile.fromFile(
            file.path,
            filename: mimeType == 'application/pdf'
                ? 'document.pdf'
                : 'receipt.jpg',
            contentType: DioMediaType.parse(mimeType),
          ),
          'type': type,
          'transaction_id': transactionId,
        }),
        options: Options(sendTimeout: const Duration(seconds: 60)),
      );
      return DocumentInfo.fromJson(response.data!);
    } on Object catch (error) {
      throw apiErrorFrom(error);
    }
  }

  @override
  Future<Uint8List> content(String documentId) async {
    final url = await contentUrl(documentId);
    try {
      final response = await _dio.get<List<int>>(
        url,
        options: Options(responseType: ResponseType.bytes),
      );
      return Uint8List.fromList(response.data!);
    } on Object catch (error) {
      throw apiErrorFrom(error);
    }
  }

  @override
  Future<String> contentUrl(String documentId) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/documents/$documentId/access-token',
      );
      final path = response.data!['content_url'] as String;
      return '${AppConfig.apiBaseUrl}${AppConfig.apiPrefix}$path';
    } on Object catch (error) {
      throw apiErrorFrom(error);
    }
  }
}

@Riverpod(keepAlive: true)
TransactionsApi transactionsApi(Ref ref) =>
    DioTransactionsApi(ref.watch(dioProvider));

@Riverpod(keepAlive: true)
DocumentsApi documentsApi(Ref ref) => DioDocumentsApi(ref.watch(dioProvider));
