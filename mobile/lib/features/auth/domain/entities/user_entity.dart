/// Pure domain entity - what the REST OF THE APP thinks a "user" is.
///
/// Deliberately has NO `fromJson`/`toJson` here - that's the data layer's
/// job (see data/models/user_model.dart). Keeping this class free of
/// serialization logic means domain/presentation code never accidentally
/// depends on the API's JSON shape - if the backend renames a field, only
/// the data layer's mapping code changes, not business logic or widgets.
class UserEntity {
  const UserEntity({
    required this.id,
    required this.phoneNumber,
    required this.displayName,
    required this.preferredLanguage,
    required this.isActive,
  });

  final String id;
  final String phoneNumber;
  final String displayName;
  final String preferredLanguage;
  final bool isActive;
}
