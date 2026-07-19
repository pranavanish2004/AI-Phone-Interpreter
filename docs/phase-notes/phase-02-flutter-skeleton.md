# Phase 2: Flutter Application (Project Skeleton)

## What Was Built

- Feature-first folder structure under `mobile/lib/features/` (auth, profile,
  call, conversation), each pre-structured with `data/domain/presentation`
  layers, populated in their dedicated later phases.
- `core/`: config (environment-aware backend URLs via `--dart-define`),
  theme, a `Failure` hierarchy for typed error handling, a `Result<T>` type
  used as the standard repository/use-case return type, DI (Riverpod
  providers for Dio), and go_router setup.
- `services/health_check_service.dart`: calls `api_gateway`'s `/health`
  endpoint - the first real end-to-end proof the client can reach the
  backend built in Phase 1.
- `ConnectivityCheckScreen`: the app's current entry screen, showing
  loading/connected/error states driven by an `AsyncNotifier`.
- Widget test covering both the success and retry-on-failure paths.
- `analysis_options.yaml` with stricter lints than default
  (`cancel_subscriptions`, `close_sinks`, `unawaited_futures`) - chosen
  specifically because upcoming phases introduce heavy Stream usage (audio,
  WebSocket) where these bugs are expensive to debug live.

## Key Decisions

| Decision | Choice | Reasoning |
|---|---|---|
| State management | Riverpod | Compile-time safety; streams-as-state fits call/caption data later |
| Routing | go_router | Centralized `redirect` guards needed once auth (Phase 4) and call state (Phase 5) exist |
| Error handling | Typed `Failure` + `Result<T>`, not thrown exceptions | Explicit, pattern-matchable failure paths across heavy async/stream code |
| Backend URL config | `--dart-define`, not hardcoded | Android emulator / iOS simulator / physical device all need different local backend addresses |

## Open Items for Later Phases

- Auth-token-attachment Dio interceptor - explicitly left as a comment
  placeholder in `dio_provider.dart`, implemented in Phase 4.
- `redirect:` auth guard in `app_router.dart` - same, Phase 4.
- WebSocket service wrapper - Phase 5, once signaling is needed.
- Code generation (`freezed`/`json_serializable`) - not run yet since no
  feature has real entities/DTOs requiring it.

## How to Verify This Phase

With the Phase 1 backend running:
```bash
cd mobile
flutter pub get
flutter test
flutter run --dart-define=API_BASE_URL=http://localhost:8000
```
Expect: app boots to a single screen showing
"Connected to api_gateway (ok)".
