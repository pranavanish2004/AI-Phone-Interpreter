import 'package:ai_interpreter/core/error/failures.dart';

/// A minimal Result type: either a success value of type [T], or a
/// [Failure]. This is our lightweight substitute for a package like
/// `dartz`'s `Either` - we don't need the full functional-programming
/// surface area, just an explicit "this call can fail" return type.
///
/// Usage pattern across the app (established here for every later phase to
/// follow):
///
/// ```dart
/// Future<Result<User>> login(String phone, String otp) async {
///   try {
///     final user = await _api.login(phone, otp);
///     return Result.success(user);
///   } on DioException catch (e) {
///     return Result.failure(mapDioErrorToFailure(e));
///   }
/// }
/// ```
///
/// And in presentation code:
///
/// ```dart
/// final result = await loginUseCase(phone, otp);
/// switch (result) {
///   case Success(:final value): // navigate to home with `value`
///   case Error(:final failure): // show failure.message
/// }
/// ```
sealed class Result<T> {
  const Result();

  factory Result.success(T value) = Success<T>;
  factory Result.failure(Failure failure) = Error<T>;

  bool get isSuccess => this is Success<T>;
  bool get isFailure => this is Error<T>;
}

class Success<T> extends Result<T> {
  const Success(this.value);
  final T value;
}

class Error<T> extends Result<T> {
  const Error(this.failure);
  final Failure failure;
}
