import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:ai_interpreter/core/router/connectivity_check_screen.dart';

/// App-wide route table.
///
/// Why go_router over Navigator 1.0 / imperative push-pop:
/// The call flow (Phase 5+) will need deep, guarded navigation - e.g.
/// redirecting away from the call screen if a call ends unexpectedly, or
/// preventing navigation back into a call screen without an active
/// call_id. go_router's declarative `redirect` mechanism handles this
/// centrally instead of scattering guard checks across every screen's
/// initState.
///
/// Routes are intentionally minimal right now - '/' is the only route,
/// showing the connectivity check screen. Each subsequent phase adds its
/// routes here:
///   Phase 4 (Auth):    /login, /otp-verify
///   Phase 2/Profile:   /profile/setup (language selection)
///   Phase 5 (Call):    /call/:callId
///   Phase 11:          /conversation/:callId/history
final appRouterProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/',
    debugLogDiagnostics: true,
    routes: [
      GoRoute(
        path: '/',
        name: 'connectivity-check',
        builder: (context, state) => const ConnectivityCheckScreen(),
      ),
    ],
    // NOTE: `redirect:` for auth-gating is added in Phase 4, once there is
    // an authState provider to redirect based on. Left unimplemented here
    // rather than stubbed with fake logic.
  );
});
