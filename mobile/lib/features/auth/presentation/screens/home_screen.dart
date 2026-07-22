import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:ai_interpreter/features/auth/presentation/providers/auth_providers.dart';

/// Deliberately minimal - this is NOT the profile or call-list feature
/// (those are separate, later phases). It exists only to prove the auth
/// flow lands somewhere real and to host a logout action, since a login
/// system without a way to log out is untestable end-to-end.
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authNotifierProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('AI Phone Interpreter'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Log out',
            onPressed: () => ref.read(authNotifierProvider.notifier).logout(),
          ),
        ],
      ),
      body: Center(
        child: switch (authState) {
          AsyncData(:final value) when value != null => Text(
              'Logged in as ${value.displayName}\n(+91 ${value.phoneNumber})',
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 18),
            ),
          _ => const CircularProgressIndicator(),
        },
      ),
    );
  }
}
