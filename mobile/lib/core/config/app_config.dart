/// Environment configuration for the app.
///
/// Why this exists:
/// The Flutter app needs to know where `api_gateway` lives, and that address
/// is DIFFERENT depending on where you're running it:
///   - Android emulator talking to a backend on your dev machine: 10.0.2.2
///   - iOS simulator talking to a backend on your dev machine: localhost
///   - A real device on the same Wi-Fi as your dev machine: your machine's LAN IP
///   - Staging/production: a real domain, e.g. api.aiinterpreter.in
///
/// Rather than hardcoding a URL and editing it by hand every time you switch
/// context (a very common source of "works on my machine" bugs), we read it
/// from `--dart-define` build-time variables, with sensible local-dev
/// defaults so `flutter run` works out of the box against the docker-compose
/// stack from Phase 1.
class AppConfig {
  AppConfig._(); // no instances - this is a static config holder

  /// Base URL for REST calls to api_gateway (Phase 1: http://localhost:8000).
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  /// Base URL for the WebSocket signaling/caption connection.
  /// Uses ws:// in dev, wss:// in production - set via --dart-define at
  /// build time for release builds.
  static const String wsBaseUrl = String.fromEnvironment(
    'WS_BASE_URL',
    defaultValue: 'ws://localhost:8000',
  );

  /// Toggles verbose logging (HTTP request/response bodies, etc). Never
  /// true in a release build - controlled by --dart-define=ENVIRONMENT=production.
  static const String environment = String.fromEnvironment(
    'ENVIRONMENT',
    defaultValue: 'development',
  );

  static bool get isProduction => environment == 'production';
}
