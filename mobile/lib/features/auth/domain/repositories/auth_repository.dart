import 'package:ai_interpreter/core/utils/result.dart';
import 'package:ai_interpreter/features/auth/domain/entities/user_entity.dart';

/// Abstract contract for authentication. Presentation-layer code (screens,
/// providers) depends on THIS interface, never on `AuthRepositoryImpl`
/// directly - the same Dependency Inversion pattern used throughout the
/// backend (MessageBroker, OTPProvider). This is what lets widget tests
/// substitute a fake repository without touching Dio or secure storage at
/// all.
abstract class AuthRepository {
  Future<Result<void>> requestOtp(String phoneNumber);

  Future<Result<UserEntity>> verifyOtp({
    required String phoneNumber,
    required String otp,
    String? displayName,
  });

  /// Returns the currently persisted user, or null if no one is logged in
  /// (no token stored, or the stored token is invalid/expired).
  Future<UserEntity?> getCurrentUser();

  Future<void> logout();
}
