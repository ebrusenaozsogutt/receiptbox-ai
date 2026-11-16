import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/widgets/app_text_field.dart';
import '../../../core/widgets/message_banner.dart';
import '../domain/validators.dart';
import 'auth_controller.dart';
import 'auth_scaffold.dart';

class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _hidePassword = true;
  bool _adultConfirmed = false;
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
          .register(
            email: _email.text.trim(),
            password: _password.text,
            isAdultConfirmed: _adultConfirmed,
          );
    } on ApiError catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AuthScaffold(
      title: 'Hesap oluştur',
      subtitle: 'Fişlerini, taksitlerini ve garantilerini tek yerde topla.',
      children: [
        Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
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
                fieldKey: const Key('register_email'),
              ),
              const SizedBox(height: AppSpacing.inputGap),
              AppTextField(
                label: 'Parola',
                hintText: 'En az 8 karakter, bir harf ve bir rakam',
                controller: _password,
                obscureText: _hidePassword,
                autofillHints: const [AutofillHints.newPassword],
                textInputAction: TextInputAction.done,
                validator: validateNewPassword,
                enabled: !_loading,
                fieldKey: const Key('register_password'),
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
              const SizedBox(height: AppSpacing.l),
              FormField<bool>(
                initialValue: _adultConfirmed,
                validator: validateAdultConfirmed,
                builder: (field) => Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    InkWell(
                      key: const Key('adult_confirmation'),
                      borderRadius: AppRadius.control,
                      onTap: _loading
                          ? null
                          : () {
                              setState(
                                () => _adultConfirmed = !_adultConfirmed,
                              );
                              field.didChange(_adultConfirmed);
                            },
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(
                          minHeight: AppSizes.minTapTarget,
                        ),
                        child: Row(
                          children: [
                            Checkbox(
                              value: _adultConfirmed,
                              onChanged: _loading
                                  ? null
                                  : (value) {
                                      setState(
                                        () => _adultConfirmed = value ?? false,
                                      );
                                      field.didChange(_adultConfirmed);
                                    },
                            ),
                            Expanded(
                              child: Text(
                                '18 yaşından büyük olduğumu onaylıyorum.',
                                style: AppTextStyles.body,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    if (field.hasError)
                      Padding(
                        padding: const EdgeInsets.only(left: AppSpacing.m),
                        child: Text(
                          field.errorText!,
                          style: AppTextStyles.bodyS.copyWith(
                            color: AppColors.danger,
                          ),
                        ),
                      ),
                  ],
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
                    : const Text('Kayıt ol'),
              ),
              const SizedBox(height: AppSpacing.s),
              TextButton(
                onPressed: _loading ? null : () => context.go('/login'),
                child: const Text('Zaten hesabın var mı? Giriş yap'),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
