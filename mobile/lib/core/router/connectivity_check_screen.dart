import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:ai_interpreter/core/di/connectivity_check_provider.dart';
import 'package:ai_interpreter/core/error/failures.dart';
import 'package:ai_interpreter/services/health_check_service.dart';

/// Phase 2's entry screen.
///
/// Why this screen exists at all, given it has no "real" product value:
/// It is the single piece of UI that proves the entire skeleton - Flutter
/// app -> Dio -> HTTP -> api_gateway container -> FastAPI health route -
/// works end-to-end, on a real device/emulator, not just in isolated unit
/// tests. Once Phase 4 (Auth) lands, this screen's role changes: the router
/// will use connectivity + auth state together to decide whether to route
/// to /login or /home. For now, it just proves the wiring and gives us a
/// visible "yes, this works" moment before we add any real features.
class ConnectivityCheckScreen extends ConsumerWidget {
  const ConnectivityCheckScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final healthState = ref.watch(connectivityCheckProvider);

    return Scaffold(
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.translate, size: 72),
              const SizedBox(height: 24),
              const Text(
                'AI Phone Interpreter',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 32),
              switch (healthState) {
                AsyncData(:final value) => _ConnectedState(health: value),
                AsyncError(:final error) => _ErrorState(error: error),
                _ => const _CheckingState(),
              },
            ],
          ),
        ),
      ),
    );
  }
}

class _CheckingState extends StatelessWidget {
  const _CheckingState();

  @override
  Widget build(BuildContext context) {
    return const Column(
      children: [
        CircularProgressIndicator(),
        SizedBox(height: 16),
        Text('Checking connection to server...'),
      ],
    );
  }
}

class _ConnectedState extends StatelessWidget {
  const _ConnectedState({required this.health});

  final BackendHealth health;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const Icon(Icons.check_circle, color: Colors.green, size: 40),
        const SizedBox(height: 12),
        Text('Connected to ${health.service} (${health.status})'),
        const SizedBox(height: 8),
        const Text(
          'Backend skeleton is reachable. Auth, profile, and calling '
          'screens arrive in later phases.',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.grey),
        ),
      ],
    );
  }
}

class _ErrorState extends ConsumerWidget {
  const _ErrorState({required this.error});

  final Object error;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final message = error is Failure
        ? (error as Failure).message
        : 'Unexpected error while checking connection.';

    return Column(
      children: [
        const Icon(Icons.error_outline, color: Colors.red, size: 40),
        const SizedBox(height: 12),
        Text(message, textAlign: TextAlign.center),
        const SizedBox(height: 16),
        ElevatedButton(
          onPressed: () => ref.read(connectivityCheckProvider.notifier).retry(),
          child: const Text('Try Again'),
        ),
      ],
    );
  }
}
