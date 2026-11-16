import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/widgets/app_text_field.dart';
import '../../../core/widgets/message_banner.dart';
import '../domain/validators.dart';
import 'auth_controller.dart';
import 'auth_scaffold.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _hidePassword = true;
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    // Hide the keyboard: it must not stay open over the next screen.
    FocusManager.instance.primaryFocus?.unfocus();
    if (_loading || !_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      // On success the router moves to Home by itself.
      await ref
          .read(authProvider.notifier)
          .login(email: _email.text.trim(), password: _password.text);
    } on ApiError catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final sessionExpired = ref.watch(authProvider).sessionExpired;
    return AuthScaffold(
      title: 'Giriş yap',
      subtitle: 'Harcamalarına ve garantilerine kaldığın yerden devam et.',
      children: [
        Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (sessionExpired && _error == null) ...[
                MessageBanner(
                  messageForCode('AUTH_EXPIRED'),
                  kind: MessageBannerKind.info,
                ),
                const SizedBox(height: AppSpacing.l),
              ],
              if (_error != null) ...[
                MessageBanner(_error!),
                const SizedBox(height: AppSpacing.l),
              ],
              AppTextField(
                label: 'E-posta',
                hintText: 'ornek@eposta.com',
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                autofillHints: const [AutofillHints.email],
                textInputAction: TextInputAction.next,
                validator: validateEmail,
                enabled: !_loading,
                fieldKey: const Key('login_email'),
              ),
              const SizedBox(height: AppSpacing.inputGap),
              AppTextField(
                label: 'Parola',
                controller: _password,
                obscureText: _hidePassword,
                autofillHints: const [AutofillHints.password],
                textInputAction: TextInputAction.done,
                onFieldSubmitted: (_) => _submit(),
                validator: validateLoginPassword,
                enabled: !_loading,
                fieldKey: const Key('login_password'),
                suffix: IconButton(
                  tooltip: _hidePassword ? 'Parolayı göster' : 'Parolayı gizle',
                  icon: Icon(
                    _hidePassword
                        ? Icons.visibility_outlined
                        : Icons.visibility_off_outlined,
                    size: AppSizes.icon,
                  ),
                  onPressed: () =>
                      setState(() => _hidePassword = !_hidePassword),
                ),
              ),
              const SizedBox(height: AppSpacing.xxl),
              FilledButton(
                onPressed: _loading ? null : _submit,
                child: _loading
                    ? const SizedBox(
                        width: AppSizes.progressSize,
                        height: AppSizes.progressSize,
                        child: CircularProgressIndicator(),
                      )
                    : const Text('Giriş yap'),
              ),
              const SizedBox(height: AppSpacing.s),
              TextButton(
                onPressed: _loading ? null : () => context.go('/register'),
                child: const Text('Hesabın yok mu? Kayıt ol'),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
