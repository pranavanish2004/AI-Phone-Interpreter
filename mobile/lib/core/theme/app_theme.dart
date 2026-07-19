import 'package:flutter/material.dart';

/// Centralized theme definitions.
///
/// Why centralize this now, even with no real UI yet:
/// Once we build the call screen (Phase 5+), it will need consistent visual
/// language for call states (connecting/connected/error), caption bubbles,
/// language badges, etc. Defining the palette and text theme once, here,
/// means every screen we build from Phase 2 onward pulls from the same
/// source instead of hardcoding colors that drift apart across features.
class AppTheme {
  AppTheme._();

  static const Color _primary = Color(0xFF3D5AFE); // indigo accent
  static const Color _secondary = Color(0xFF00BFA5); // teal accent

  static ThemeData get light {
    final base = ThemeData(
      brightness: Brightness.light,
      useMaterial3: true,
      colorSchemeSeed: _primary,
    );

    return base.copyWith(
      colorScheme: base.colorScheme.copyWith(secondary: _secondary),
      appBarTheme: const AppBarTheme(
        centerTitle: true,
        elevation: 0,
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
      ),
    );
  }

  static ThemeData get dark {
    final base = ThemeData(
      brightness: Brightness.dark,
      useMaterial3: true,
      colorSchemeSeed: _primary,
    );
    return base;
  }
}
