/// Base class for all "expected" failures in the app - i.e. things that can
/// go wrong that we WANT to handle gracefully and show the user something
/// meaningful about, as opposed to unexpected bugs (which should just throw
/// and surface in crash reporting).
///
/// Why not just throw exceptions everywhere:
/// Throwing/catching generic exceptions across async boundaries (especially
/// with streams, which this app will have a LOT of - audio streams, caption
/// streams, call-status streams) gets messy fast, and it's easy to
/// accidentally swallow a real bug inside a broad catch block. Modeling
/// failures as typed, returned values (used together with Dart's pattern
/// matching) makes every failure path explicit and testable.
sealed class Failure {
  const Failure(this.message);

  final String message;
}

/// The backend was unreachable, timed out, or returned a network-layer
/// error (DNS failure, connection refused, etc) - as opposed to a valid
/// HTTP response with an error status code.
class NetworkFailure extends Failure {
  const NetworkFailure([super.message = 'Could not reach the server. Check your connection.']);
}

/// The backend responded, but with an error status code (4xx/5xx).
class ServerFailure extends Failure {
  const ServerFailure(super.message, {this.statusCode});

  final int? statusCode;
}

/// Authentication-specific failure - e.g. expired token, invalid OTP.
/// Kept distinct from ServerFailure so the UI/router can react specifically
/// (redirect to login) rather than just showing a generic error banner.
class AuthFailure extends Failure {
  const AuthFailure(super.message);
}

/// Input failed local validation before a request was even sent (e.g.
/// malformed phone number). Kept distinct so the UI can show inline field
/// errors instead of a full-screen error state.
class ValidationFailure extends Failure {
  const ValidationFailure(super.message);
}

/// Catch-all for anything unexpected. Should be rare in practice - if you
/// find yourself returning this often, it usually means a new Failure
/// subtype should be added instead.
class UnknownFailure extends Failure {
  const UnknownFailure([super.message = 'Something went wrong. Please try again.']);
}
