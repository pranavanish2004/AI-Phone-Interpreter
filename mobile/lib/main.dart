import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:ai_interpreter/app.dart';

/// Entry point.
///
/// ProviderScope must wrap the entire app exactly once, at the root - it's
/// what holds the state of every Riverpod provider we define across every
/// feature. Forgetting this is the single most common Riverpod setup
/// mistake, so it lives right here in main.dart where it can't be missed.
void main() {
  runApp(const ProviderScope(child: App()));
}
