import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:ai_interpreter/core/utils/result.dart';
import 'package:ai_interpreter/features/auth/presentation/providers/auth_providers.dart';

/// Step 2 of login: enter the OTP (and, for a first-time user, a display
/// name). On success, the AuthNotifier's state updates to a non-null
/// UserEntity, which the router's redirect guard (added below in
/// app_router.dart) picks up automatically to navigate into the app - this
/// screen doesn't need to manually navigate on success.
class OtpVerifyScreen extends ConsumerStatefulWidget {
  const OtpVerifyScreen({super.key, required this.phoneNumber});

  final String phoneNumber;

  @override
  ConsumerState<OtpVerifyScreen> createState() => _OtpVerifyScreenState();
}

class _OtpVerifyScreenState extends ConsumerState<OtpVerifyScreen> {
  final _otpController = TextEditingController();
  final _nameController = TextEditingController();
  bool _isSubmitting = false;
  String? _errorText;

  @override
  void dispose() {
    _otpController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final otp = _otpController.text.trim();
    if (otp.length < 4) {
      setState(() => _errorText = 'Enter the code we sent you');
      return;
    }

    setState(() {
      _isSubmitting = true;
      _errorText = null;
    });

    final displayName = _nameController.text.trim();
    final result = await ref.read(authNotifierProvider.notifier).verifyOtp(
          phoneNumber: widget.phoneNumber,
          otp: otp,
          displayName: displayName.isEmpty ? null : displayName,
        );

    if (!mounted) return;
    setState(() => _isSubmitting = false);

    if (result case Error(:final failure)) {
      setState(() => _errorText = failure.message);
    }
    // On Success, no manual navigation needed - the router's redirect
    // guard reacts to authNotifierProvider's state change automatically.
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Verify')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              'Enter the code sent to +91 ${widget.phoneNumber}',
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 16),
            ),
            const SizedBox(height: 24),
            TextField(
              controller: _otpController,
              keyboardType: TextInputType.number,
              maxLength: 6,
              decoration: InputDecoration(
                border: const OutlineInputBorder(),
                labelText: 'OTP',
                errorText: _errorText,
              ),
            ),
            const SizedBox(height: 16),
            // Shown for every attempt (we don't know client-side whether
            // this phone number is new) - the backend simply ignores this
            // field for an existing user, per AuthService's design
            // (Phase 4): required only for first-time registration.
            TextField(
              controller: _nameController,
              decoration: const InputDecoration(
                border: OutlineInputBorder(),
                labelText: 'Your name (only needed the first time)',
              ),
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _isSubmitting ? null : _submit,
              child: _isSubmitting
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Verify & Continue'),
            ),
          ],
        ),
      ),
    );
  }
}
