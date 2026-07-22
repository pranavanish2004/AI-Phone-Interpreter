import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:ai_interpreter/core/error/failures.dart';
import 'package:ai_interpreter/core/utils/result.dart';
import 'package:ai_interpreter/features/auth/presentation/providers/auth_providers.dart';

/// Step 1 of login: collect an India mobile number, request an OTP, then
/// navigate to the OTP verification screen.
///
/// Kept as a StatefulWidget (not a Riverpod-consuming stateless widget)
/// because the text field's controller and a local "is submitting" flag
/// are pure UI/local state - they don't belong in a Riverpod provider that
/// would outlive this screen.
class PhoneEntryScreen extends ConsumerStatefulWidget {
  const PhoneEntryScreen({super.key});

  @override
  ConsumerState<PhoneEntryScreen> createState() => _PhoneEntryScreenState();
}

class _PhoneEntryScreenState extends ConsumerState<PhoneEntryScreen> {
  final _phoneController = TextEditingController();
  bool _isSubmitting = false;
  String? _errorText;

  @override
  void dispose() {
    _phoneController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final phone = _phoneController.text.trim();
    if (phone.length < 10) {
      setState(() => _errorText = 'Enter a valid 10-digit mobile number');
      return;
    }

    setState(() {
      _isSubmitting = true;
      _errorText = null;
    });

    final result = await ref.read(authNotifierProvider.notifier).requestOtp(phone);

    if (!mounted) return;
    setState(() => _isSubmitting = false);

    switch (result) {
      case Success():
        context.push('/otp-verify', extra: phone);
      case Error(:final failure):
        setState(() => _errorText = failure.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Welcome')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.translate, size: 64),
            const SizedBox(height: 16),
            const Text(
              'Enter your mobile number',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            const Text(
              "We'll send you a one-time code to verify it's you.",
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey),
            ),
            const SizedBox(height: 24),
            TextField(
              controller: _phoneController,
              keyboardType: TextInputType.phone,
              maxLength: 10,
              decoration: InputDecoration(
                prefixText: '+91 ',
                border: const OutlineInputBorder(),
                labelText: 'Mobile number',
                errorText: _errorText,
              ),
              onSubmitted: (_) => _submit(),
            ),
            const SizedBox(height: 8),
            ElevatedButton(
              onPressed: _isSubmitting ? null : _submit,
              child: _isSubmitting
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Send OTP'),
            ),
          ],
        ),
      ),
    );
  }
}
