import 'package:dio/dio.dart';

import 'package:ai_interpreter/core/error/failures.dart';
import 'package:ai_interpreter/core/utils/result.dart';
import 'package:ai_interpreter/features/auth/data/models/user_model.dart';
import 'package:ai_interpreter/features/auth/data/token_storage_service.dart';
import 'package:ai_interpreter/features/auth/domain/entities/user_entity.dart';
import 'package:ai_interpreter/features/auth/domain/repositories/auth_repository.dart';

class AuthRepositoryImpl implements AuthRepository {
  AuthRepositoryImpl(this._dio, this._tokenStorage);

  final Dio _dio;
  final TokenStorageService _tokenStorage;

  @override
  Future<Result<void>> requestOtp(String phoneNumber) async {
    try {
      await _dio.post(
        '/api/v1/auth/otp/request',
        data: {'phone_number': phoneNumber},
      );
      return const Result.success(null);
    } on DioException catch (e) {
      return Result.failure(_mapDioError(e));
    }
  }

  @override
  Future<Result<UserEntity>> verifyOtp({
    required String phoneNumber,
    required String otp,
    String? displayName,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/api/v1/auth/otp/verify',
        data: {
          'phone_number': phoneNumber,
          'otp': otp,
          if (displayName != null) 'display_name': displayName,
        },
      );

      final body = response.data!;
      final token = body['access_token'] as String;
      final user = UserModel.fromJson(body['user'] as Map<String, dynamic>);

      // Persist the token BEFORE returning success - any caller that
      // observes a successful Result can safely assume the token is
      // already stored and future requests will be authenticated.
      await _tokenStorage.saveToken(token);

      return Result.success(user.toEntity());
    } on DioException catch (e) {
      return Result.failure(_mapDioError(e));
    }
  }

  @override
  Future<UserEntity?> getCurrentUser() async {
    final token = await _tokenStorage.readToken();
    if (token == null) return null;

    try {
      // The auth interceptor (see core/di/dio_provider.dart) attaches this
      // token automatically - we don't need to pass it manually here.
      final response = await _dio.get<Map<String, dynamic>>('/api/v1/auth/me');
      return UserModel.fromJson(response.data!).toEntity();
    } on DioException catch (e) {
      // A 401 here specifically means the stored token is invalid/expired
      // - clear it so we don't keep retrying with a dead token on every
      // app launch.
      if (e.response?.statusCode == 401) {
        await _tokenStorage.clearToken();
      }
      return null;
    }
  }

  @override
  Future<void> logout() => _tokenStorage.clearToken();

  Failure _mapDioError(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.connectionError:
        return const NetworkFailure();
      case DioExceptionType.badResponse:
        final data = e.response?.data;
        final message = (data is Map && data['message'] is String)
            ? data['message'] as String
            : 'Something went wrong. Please try again.';
        final errorCode = (data is Map && data['error_code'] is String)
            ? data['error_code'] as String
            : null;

        // Maps the backend's error_code (see api_gateway's AppException
        // hierarchy, Phase 3) onto the appropriate Flutter Failure type -
        // this is the payoff of both sides agreeing on a consistent error
        // contract from the start.
        if (errorCode == 'UNAUTHORIZED') return AuthFailure(message);
        if (errorCode == 'VALIDATION_ERROR' ||
            errorCode == 'REQUEST_VALIDATION_ERROR') {
          return ValidationFailure(message);
        }
        return ServerFailure(message, statusCode: e.response?.statusCode);
      default:
        return const UnknownFailure();
    }
  }
}
