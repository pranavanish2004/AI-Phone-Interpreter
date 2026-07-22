import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:ai_interpreter/core/router/connectivity_check_screen.dart';
import 'package:ai_interpreter/features/auth/presentation/providers/auth_providers.dart';
import 'package:ai_interpreter/features/auth/presentation/screens/home_screen.dart';
import 'package:ai_interpreter/features/auth/presentation/screens/otp_verify_screen.dart';
import 'package:ai_interpreter/features/auth/presentation/screens/phone_entry_screen.dart';

/// App-wide route table.
///
/// Routes:
///   /                 connectivity check (Phase 2) - dev/debug entry point
///   /login            phone number entry (Phase 4)
///   /otp-verify        OTP entry, expects `extra: phoneNumber` (Phase 4)
///   /home              minimal authenticated landing screen (Phase 4)
///   Phase 2/Profile:   /profile/setup (language selection)
///   Phase 5 (Call):    /call/:callId
///   Phase 11:          /conversation/:callId/history
final appRouterProvider = Provider<GoRouter>((ref) {
  // `refreshListenable` isn't used here because Riverpod's ref.watch inside
  // `redirect` already causes GoRouter to re-evaluate whenever
  // authNotifierProvider's state changes - no separate ChangeNotifier
  // bridge needed.
  return GoRouter(
    initialLocation: '/home',
    debugLogDiagnostics: true,
    redirect: (context, state) {
      final authState = ref.watch(authNotifierProvider);

      // While we don't yet know the auth state (checking stored token on
      // startup), don't redirect anywhere - let the current route render
      // its own loading state rather than flashing to /login and back.
      if (authState.isLoading) return null;

      final isLoggedIn = authState.valueOrNull != null;
      final isOnAuthRoute = state.matchedLocation == '/login' ||
          state.matchedLocation == '/otp-verify';

      if (!isLoggedIn && !isOnAuthRoute && state.matchedLocation != '/') {
        return '/login';
      }
      if (isLoggedIn && isOnAuthRoute) {
        return '/home';
      }
      return null;
    },
    routes: [
      GoRoute(
        path: '/',
        name: 'connectivity-check',
        builder: (context, state) => const ConnectivityCheckScreen(),
      ),
      GoRoute(
        path: '/login',
        name: 'login',
        builder: (context, state) => const PhoneEntryScreen(),
      ),
      GoRoute(
        path: '/otp-verify',
        name: 'otp-verify',
        builder: (context, state) => OtpVerifyScreen(phoneNumber: state.extra as String),
      ),
      GoRoute(
        path: '/home',
        name: 'home',
        builder: (context, state) => const HomeScreen(),
      ),
    ],
  );
});
