import 'package:ai_interpreter/features/auth/domain/entities/user_entity.dart';

/// Data-layer model: knows how to parse the backend's JSON shape.
///
/// Written by hand (no json_serializable codegen) deliberately for this
/// phase - the shape is small and stable, and avoiding `build_runner`
/// keeps the auth feature runnable without a code-gen step. If/when models
/// grow more complex (nested objects, many optional fields), switching to
/// `@JsonSerializable` is a mechanical change contained entirely to this
/// file - nothing outside the data layer would need to change.
class UserModel {
  const UserModel({
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

  factory UserModel.fromJson(Map<String, dynamic> json) => UserModel(
        id: json['id'] as String,
        phoneNumber: json['phone_number'] as String,
        displayName: json['display_name'] as String,
        preferredLanguage: json['preferred_language'] as String,
        isActive: json['is_active'] as bool,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'phone_number': phoneNumber,
        'display_name': displayName,
        'preferred_language': preferredLanguage,
        'is_active': isActive,
      };

  UserEntity toEntity() => UserEntity(
        id: id,
        phoneNumber: phoneNumber,
        displayName: displayName,
        preferredLanguage: preferredLanguage,
        isActive: isActive,
      );
}
