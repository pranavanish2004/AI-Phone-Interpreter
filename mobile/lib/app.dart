import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:ai_interpreter/core/router/app_router.dart';
import 'package:ai_interpreter/core/theme/app_theme.dart';

/// Root widget of the application.
///
/// Kept deliberately thin: its only job is to wire MaterialApp.router to
/// our go_router instance and our theme. Any real logic belongs in
/// providers/services/features, not here - this file should stay stable
/// even as the app grows to dozens of screens.
class App extends ConsumerWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(appRouterProvider);

    return MaterialApp.router(
      title: 'AI Phone Interpreter',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: ThemeMode.system,
      routerConfig: router,
    );
  }
}
