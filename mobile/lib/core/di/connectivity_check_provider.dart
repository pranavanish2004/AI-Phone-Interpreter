import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:ai_interpreter/core/utils/result.dart';
import 'package:ai_interpreter/services/health_check_service.dart';

/// Drives the "checking backend connectivity" screen.
///
/// Why AsyncNotifier and not just a FutureProvider:
/// We want an explicit `retry()` action the user can trigger from the UI
/// (e.g. tapping a "Try Again" button if the backend was down), which
/// AsyncNotifier supports naturally via `state = const AsyncLoading()` +
/// re-running the check. A plain FutureProvider would require `ref.refresh`
/// wired from outside, which is less discoverable for this use case.
class ConnectivityCheckNotifier extends AsyncNotifier<BackendHealth> {
  @override
  Future<BackendHealth> build() => _check();

  Future<BackendHealth> _check() async {
    final service = ref.read(healthCheckServiceProvider);
    final result = await service.checkApiGateway();

    switch (result) {
      case Success(:final value):
        return value;
      case Error(:final failure):
        // Re-throwing here is intentional and idiomatic for AsyncNotifier:
        // it converts into an AsyncError state that the UI can pattern-match
        // on, carrying `failure.message` for display.
        throw failure;
    }
  }

  Future<void> retry() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(_check);
  }
}

final connectivityCheckProvider =
    AsyncNotifierProvider<ConnectivityCheckNotifier, BackendHealth>(
  ConnectivityCheckNotifier.new,
);
