import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ai_interpreter/core/di/connectivity_check_provider.dart';
import 'package:ai_interpreter/core/error/failures.dart';
import 'package:ai_interpreter/core/router/connectivity_check_screen.dart';
import 'package:ai_interpreter/services/health_check_service.dart';

void main() {
  group('ConnectivityCheckScreen', () {
    testWidgets('shows success state when backend responds healthy',
        (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            // Overriding the AsyncNotifier's underlying data directly
            // (rather than mocking Dio) keeps this a pure WIDGET test - it
            // verifies the screen renders correctly given a state, not
            // that networking works (that belongs in a HealthCheckService
            // unit test, added alongside Phase 4's auth tests).
            connectivityCheckProvider.overrideWith(
              () => _FakeConnectivityNotifier(
                const AsyncData(
                  BackendHealth(service: 'api_gateway', status: 'ok'),
                ),
              ),
            ),
          ],
          child: const MaterialApp(home: ConnectivityCheckScreen()),
        ),
      );

      expect(find.textContaining('Connected to api_gateway'), findsOneWidget);
    });

    testWidgets('shows retry button on failure and calls retry on tap',
        (tester) async {
      var retryCalled = false;

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            connectivityCheckProvider.overrideWith(
              () => _FakeConnectivityNotifier(
                AsyncError(const NetworkFailure(), StackTrace.empty),
                onRetry: () => retryCalled = true,
              ),
            ),
          ],
          child: const MaterialApp(home: ConnectivityCheckScreen()),
        ),
      );

      expect(find.text('Try Again'), findsOneWidget);

      await tester.tap(find.text('Try Again'));
      await tester.pump();

      expect(retryCalled, isTrue);
    });
  });
}

/// Test double for ConnectivityCheckNotifier that lets us inject a fixed
/// AsyncValue state instead of performing a real network call.
class _FakeConnectivityNotifier extends ConnectivityCheckNotifier {
  _FakeConnectivityNotifier(this._initialState, {this.onRetry});

  final AsyncValue<BackendHealth> _initialState;
  final VoidCallback? onRetry;

  @override
  Future<BackendHealth> build() {
    Future.microtask(() => state = _initialState);
    // build() must return a Future<BackendHealth>; since we override state
    // immediately after, this initial throw-away value is never shown.
    return _initialState.maybeWhen(
      data: (value) => Future.value(value),
      orElse: () => Future.error(const UnknownFailure()),
    );
  }

  @override
  Future<void> retry() async {
    onRetry?.call();
  }
}
