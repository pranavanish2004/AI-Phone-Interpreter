# AI Phone Interpreter - Flutter Client

## Architecture

Feature-first + Clean Architecture layers within each feature:

```
lib/
├── core/                  # Cross-cutting: config, DI, error types, router, theme, utils
├── features/
│   ├── auth/              # Reserved for Phase 4
│   ├── profile/           # Reserved for language preference / profile phase
│   ├── call/               # Reserved for Phase 5+ (WebRTC)
│   └── conversation/       # Reserved for Phase 11 (context/history UI)
│       Each feature: data/ (repos+DTOs) -> domain/ (entities+usecases) -> presentation/ (UI+providers)
├── services/               # Cross-feature infrastructure services (e.g. health check)
├── app.dart                # Root widget: theme + router wiring
└── main.dart                # Entry point: ProviderScope
```

State management: **Riverpod**. Routing: **go_router**. Networking: **Dio**
(REST) + **web_socket_channel** (added when Phase 5 needs it).

## Running Locally

1. Make sure the backend from Phase 1 is running:
   ```bash
   docker compose -f ../docker/docker-compose.yml --env-file ../.env up
   ```
2. Install dependencies:
   ```bash
   flutter pub get
   ```
3. Run against your target:

   **Android emulator** (10.0.2.2 maps to your host machine):
   ```bash
   flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000 --dart-define=WS_BASE_URL=ws://10.0.2.2:8000
   ```

   **iOS simulator** (localhost works directly):
   ```bash
   flutter run --dart-define=API_BASE_URL=http://localhost:8000 --dart-define=WS_BASE_URL=ws://localhost:8000
   ```

   **Physical device on same Wi-Fi** (replace with your machine's LAN IP):
   ```bash
   flutter run --dart-define=API_BASE_URL=http://192.168.1.X:8000 --dart-define=WS_BASE_URL=ws://192.168.1.X:8000
   ```

You should see "Connected to api_gateway (ok)" on screen - this confirms
the full chain (Flutter -> Dio -> HTTP -> api_gateway container ->
FastAPI `/health` route) works.

## Testing

```bash
flutter test
```

Phase 2 includes a widget test for the connectivity check screen, covering
both the success state and the retry-on-failure interaction.

## What's NOT Here Yet (by design)

- No authentication (Phase 4)
- No language preference / profile UI (dedicated phase)
- No call screen / WebRTC (Phase 5+)
- No code generation output committed (`*.g.dart`, `*.freezed.dart`) - run
  `dart run build_runner build --delete-conflicting-outputs` once a feature
  phase introduces `@freezed`/`@JsonSerializable` classes that need it.
