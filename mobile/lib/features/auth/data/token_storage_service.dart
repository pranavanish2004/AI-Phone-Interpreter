import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Wraps flutter_secure_storage for the ONE thing we store securely: the
/// JWT access token.
///
/// Why not just call FlutterSecureStorage directly from AuthRepositoryImpl:
/// Isolating storage access behind this small class means Phase 5+ (which
/// may need to read the token to attach it to a WebSocket connection URL,
/// separate from Dio's interceptor) has one obvious place to get it from,
/// and if we ever need to migrate storage mechanisms, only this file
/// changes.
class TokenStorageService {
  TokenStorageService(this._storage);

  final FlutterSecureStorage _storage;

  static const _tokenKey = 'auth_access_token';

  Future<void> saveToken(String token) => _storage.write(key: _tokenKey, value: token);

  Future<String?> readToken() => _storage.read(key: _tokenKey);

  Future<void> clearToken() => _storage.delete(key: _tokenKey);
}

final tokenStorageServiceProvider = Provider<TokenStorageService>((ref) {
  return TokenStorageService(const FlutterSecureStorage());
});
