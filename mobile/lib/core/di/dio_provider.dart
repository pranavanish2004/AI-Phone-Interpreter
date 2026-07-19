import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:ai_interpreter/core/config/app_config.dart';

/// Provides a single, app-wide configured [Dio] instance.
///
/// Why a provider instead of a global singleton or `Dio()` created inline
/// wherever needed:
/// 1. Testability - tests can override this provider with a mocked Dio
///    (via `dio_adapter` or a fake) without touching real network calls.
/// 2. Single source of truth for base URL, timeouts, and interceptors -
///    every repository in every feature gets the SAME configured client,
///    so auth-token-attachment (added in Phase 4) only needs to be written
///    once, here, rather than duplicated per feature.
final dioProvider = Provider<Dio>((ref) {
  final dio = Dio(
    BaseOptions(
      baseUrl: AppConfig.apiBaseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 15),
      headers: {'Content-Type': 'application/json'},
    ),
  );

  // Only log request/response bodies in development - never in production,
  // where this could leak sensitive data (tokens, phone numbers) into
  // device logs.
  if (!AppConfig.isProduction) {
    dio.interceptors.add(
      LogInterceptor(
        requestBody: true,
        responseBody: true,
        error: true,
      ),
    );
  }

  // NOTE: an auth-token-attachment interceptor (reading the JWT from
  // flutter_secure_storage and setting the Authorization header) is added
  // in Phase 4, once the auth feature actually issues tokens. Left as an
  // explicit placeholder here rather than guessed at now.

  return dio;
});
