import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:ai_interpreter/core/config/app_config.dart';
import 'package:ai_interpreter/features/auth/data/token_storage_service.dart';

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

  // Attaches the JWT access token (if one is stored) to every outgoing
  // request. Kept here, at the single shared Dio instance, rather than
  // added manually to each repository call - this was left as an explicit
  // placeholder in Phase 3 specifically so it landed here, once
  // TokenStorageService existed to read from.
  dio.interceptors.add(
    InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await ref.read(tokenStorageServiceProvider).readToken();
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        handler.next(options);
      },
    ),
  );

  return dio;
});
