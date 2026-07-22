import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:ai_interpreter/core/di/dio_provider.dart';
import 'package:ai_interpreter/core/error/failures.dart';
import 'package:ai_interpreter/core/utils/result.dart';

/// Result payload of a successful health check against api_gateway.
class BackendHealth {
  const BackendHealth({required this.service, required this.status});

  final String service;
  final String status;

  factory BackendHealth.fromJson(Map<String, dynamic> json) => BackendHealth(
        service: json['service'] as String,
        status: json['status'] as String,
      );
}

/// Thin service wrapping the `/health` endpoint on api_gateway.
///
/// Why this exists as a standalone service (not folded into a feature):
/// This isn't tied to any one feature - it's infrastructure used to verify
/// the app can reach the backend AT ALL, useful both as a Phase 2
/// "does the skeleton work end-to-end" check and later as a real
/// connectivity indicator in the UI (e.g. a banner when the backend is
/// unreachable mid-call).
class HealthCheckService {
  HealthCheckService(this._dio);

  final Dio _dio;

  Future<Result<BackendHealth>> checkApiGateway() async {
    try {
      final response = await _dio.get<Map<String, dynamic>>('/health');
      final health = BackendHealth.fromJson(response.data!);
      return Result.success(health);
    } on DioException catch (e) {
      return Result.failure(_mapDioError(e));
    } catch (_) {
      return const Result.failure(UnknownFailure());
    }
  }

  Failure _mapDioError(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.connectionError:
        return const NetworkFailure();
      case DioExceptionType.badResponse:
        return ServerFailure(
          'Server returned an error',
          statusCode: e.response?.statusCode,
        );
      default:
        return const UnknownFailure();
    }
  }
}

final healthCheckServiceProvider = Provider<HealthCheckService>((ref) {
  final dio = ref.watch(dioProvider);
  return HealthCheckService(dio);
});
