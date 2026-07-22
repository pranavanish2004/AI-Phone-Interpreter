import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:ai_interpreter/core/di/dio_provider.dart';
import 'package:ai_interpreter/core/utils/result.dart';
import 'package:ai_interpreter/features/auth/data/repositories/auth_repository_impl.dart';
import 'package:ai_interpreter/features/auth/data/token_storage_service.dart';
import 'package:ai_interpreter/features/auth/domain/entities/user_entity.dart';
import 'package:ai_interpreter/features/auth/domain/repositories/auth_repository.dart';

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  final dio = ref.watch(dioProvider);
  final tokenStorage = ref.watch(tokenStorageServiceProvider);
  return AuthRepositoryImpl(dio, tokenStorage);
});

/// The app-wide auth state: null means "not logged in", a UserEntity means
/// "logged in as this user". This is what `app_router.dart`'s redirect
/// guard watches to decide whether to show /login or the authenticated
/// app.
class AuthNotifier extends AsyncNotifier<UserEntity?> {
  @override
  Future<UserEntity?> build() {
    // On app startup, check if a token is already stored and still valid -
    // this is what lets a returning user skip the login screen entirely.
    return ref.read(authRepositoryProvider).getCurrentUser();
  }

  Future<Result<void>> requestOtp(String phoneNumber) {
    return ref.read(authRepositoryProvider).requestOtp(phoneNumber);
  }

  Future<Result<UserEntity>> verifyOtp({
    required String phoneNumber,
    required String otp,
    String? displayName,
  }) async {
    final result = await ref.read(authRepositoryProvider).verifyOtp(
          phoneNumber: phoneNumber,
          otp: otp,
          displayName: displayName,
        );

    // On success, update our own state immediately so the router guard
    // reacts right away, rather than waiting for something else to
    // refresh this provider.
    if (result case Success(:final value)) {
      state = AsyncData(value);
    }

    return result;
  }

  Future<void> logout() async {
    await ref.read(authRepositoryProvider).logout();
    state = const AsyncData(null);
  }
}

final authNotifierProvider = AsyncNotifierProvider<AuthNotifier, UserEntity?>(
  AuthNotifier.new,
);
