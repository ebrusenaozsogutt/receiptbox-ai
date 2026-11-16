import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../theme/app_colors.dart';
import '../theme/app_dimens.dart';
import '../theme/app_text_styles.dart';

/// A labelled text field as designed in Figma: the label sits above the box.
class AppTextField extends StatelessWidget {
  const AppTextField({
    super.key,
    required this.label,
    required this.controller,
    this.hintText,
    this.validator,
    this.keyboardType,
    this.obscureText = false,
    this.suffix,
    this.autofillHints,
    this.textInputAction,
    this.onFieldSubmitted,
    this.enabled = true,
    this.inputFormatters,
    this.fieldKey,
  });

  final String label;
  final TextEditingController controller;
  final String? hintText;
  final FormFieldValidator<String>? validator;
  final TextInputType? keyboardType;
  final bool obscureText;
  final Widget? suffix;
  final Iterable<String>? autofillHints;
  final TextInputAction? textInputAction;
  final ValueChanged<String>? onFieldSubmitted;
  final bool enabled;
  final List<TextInputFormatter>? inputFormatters;
  final Key? fieldKey;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: AppTextStyles.label.copyWith(color: AppColors.textMuted),
        ),
        const SizedBox(height: AppSpacing.xs),
        TextFormField(
          key: fieldKey,
          controller: controller,
          validator: validator,
          keyboardType: keyboardType,
          obscureText: obscureText,
          autofillHints: autofillHints,
          textInputAction: textInputAction,
          onFieldSubmitted: onFieldSubmitted,
          enabled: enabled,
          inputFormatters: inputFormatters,
          style: AppTextStyles.body,
          decoration: InputDecoration(hintText: hintText, suffixIcon: suffix),
        ),
      ],
    );
  }
}
