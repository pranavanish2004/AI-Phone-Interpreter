import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'package:ai_interpreter/core/error/failures.dart';
import 'package:ai_interpreter/core/utils/result.dart';
import 'package:ai_interpreter/features/auth/domain/entities/user_entity.dart';
import 'package:ai_interpreter/features/auth/domain/repositories/auth_repository.dart';
import 'package:ai_interpreter/features/auth/presentation/providers/auth_providers.dart';
import 'package:ai_interpreter/features/auth/presentation/screens/otp_verify_screen.dart';
import 'package:ai_interpreter/features/auth/presentation/screens/phone_entry_screen.dart';

/// Fake repository - lets these tests verify screen behavior without any
/// real Dio/HTTP/secure-storage involvement, consistent with how the
/// backend's tests substitute fakes behind an interface (OTPProvider,
/// MessageBroker) rather than mocking library internals.
class _FakeAuthRepository implements AuthRepository {
  _FakeAuthRepository({this.otpResult, this.verifyResult});

  final Result<void>? otpResult;
  final Result<UserEntity>? verifyResult;
  String? lastRequestedPhone;

  @override
  Future<Result<void>> requestOtp(String phoneNumber) async {
    lastRequestedPhone = phoneNumber;
    return otpResult ?? const Result.success(null);
  }

  @override
  Future<Result<UserEntity>> verifyOtp({
    required String phoneNumber,
    required String otp,
    String? displayName,
  }) async {
    return verifyResult ??
        const Result.failure(UnknownFailure());
  }

  @override
  Future<UserEntity?> getCurrentUser() async => null;

  @override
  Future<void> logout() async {}
}

void main() {
  group('PhoneEntryScreen', () {
    testWidgets('shows validation error for a too-short number', (tester) async {
      final fakeRepo = _FakeAuthRepository();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [authRepositoryProvider.overrideWithValue(fakeRepo)],
          child: MaterialApp(
            home: const PhoneEntryScreen(),
          ),
        ),
      );

      await tester.enterText(find.byType(TextField), '123');
      await tester.tap(find.text('Send OTP'));
      await tester.pump();

      expect(find.text('Enter a valid 10-digit mobile number'), findsOneWidget);
      expect(fakeRepo.lastRequestedPhone, isNull); // never called the repo
    });

    testWidgets('calls requestOtp with the entered number', (tester) async {
      final fakeRepo = _FakeAuthRepository();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [authRepositoryProvider.overrideWithValue(fakeRepo)],
          child: MaterialApp.router(
            routerConfig: GoRouter(
              initialLocation: '/login',
              routes: [
                GoRoute(path: '/login', builder: (c, s) => const PhoneEntryScreen()),
                GoRoute(
                  path: '/otp-verify',
                  builder: (c, s) => OtpVerifyScreen(phoneNumber: s.extra as String),
                ),
              ],
            ),
          ),
        ),
      );

      await tester.enterText(find.byType(TextField), '9876543210');
      await tester.tap(find.text('Send OTP'));
      await tester.pumpAndSettle();

      expect(fakeRepo.lastRequestedPhone, '9876543210');
      // Successful request navigates to the OTP screen.
      expect(find.byType(OtpVerifyScreen), findsOneWidget);
    });
  });

  group('OtpVerifyScreen', () {
    testWidgets('shows failure message on invalid OTP', (tester) async {
      final fakeRepo = _FakeAuthRepository(
        verifyResult: const Result.failure(ValidationFailure('Invalid or expired OTP.')),
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [authRepositoryProvider.overrideWithValue(fakeRepo)],
          child: const MaterialApp(
            home: OtpVerifyScreen(phoneNumber: '9876543210'),
          ),
        ),
      );

      await tester.enterText(find.byType(TextField).first, '000000');
      await tester.tap(find.text('Verify & Continue'));
      await tester.pump();

      expect(find.text('Invalid or expired OTP.'), findsOneWidget);
    });
  });
}
