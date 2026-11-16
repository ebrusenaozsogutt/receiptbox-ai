/// The signed-in user as returned by `GET /me`. (The backend never sends the password.)
class UserProfile {
  const UserProfile({
    required this.id,
    required this.email,
    required this.isAdultConfirmed,
    required this.createdAt,
  });

  final String id;
  final String email;
  final bool isAdultConfirmed;
  final DateTime createdAt;

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      id: json['id'] as String,
      email: json['email'] as String,
      isAdultConfirmed: json['is_adult_confirmed'] as bool,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}
