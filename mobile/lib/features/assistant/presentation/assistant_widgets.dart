import 'package:material_ui/material_ui.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../domain/assistant_models.dart';
import 'assistant_actions.dart';

/// The user's question, on the right.
class QuestionBubble extends StatelessWidget {
  const QuestionBubble({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        constraints: const BoxConstraints(
          maxWidth: AppSizes.chatBubbleMaxWidth,
        ),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.l,
          vertical: AppSpacing.m,
        ),
        decoration: BoxDecoration(
          color: AppColors.primary,
          borderRadius: AppRadius.card,
        ),
        child: Text(
          text,
          style: AppTextStyles.body.copyWith(color: AppColors.onPrimary),
        ),
      ),
    );
  }
}

/// The assistant's answer, on the left, with its buttons underneath.
class AnswerBubble extends StatelessWidget {
  const AnswerBubble({super.key, required this.reply, required this.onAction});

  final AssistantReply reply;
  final void Function(AssistantAction action) onAction;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          maxWidth: AppSizes.chatBubbleMaxWidth,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.l,
                vertical: AppSpacing.m,
              ),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: AppRadius.card,
                border: Border.all(color: AppColors.border),
              ),
              child: SelectableText(reply.answer, style: AppTextStyles.body),
            ),
            if (reply.actions.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.s),
              Wrap(
                spacing: AppSpacing.s,
                runSpacing: AppSpacing.s,
                children: [
                  for (var i = 0; i < reply.actions.length; i++)
                    OutlinedButton.icon(
                      key: Key('assistant_action_$i'),
                      onPressed: () => onAction(reply.actions[i]),
                      icon: Icon(
                        assistantActionIcon(reply.actions[i].type),
                        size: AppSizes.iconS,
                      ),
                      label: Text(reply.actions[i].label),
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// A question that got no answer: the reason and "Tekrar dene".
class ErrorBubble extends StatelessWidget {
  const ErrorBubble({super.key, required this.message, this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        key: const Key('assistant_error'),
        constraints: const BoxConstraints(
          maxWidth: AppSizes.chatBubbleMaxWidth,
        ),
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.l,
          AppSpacing.m,
          AppSpacing.s,
          AppSpacing.xxs,
        ),
        decoration: BoxDecoration(
          color: AppColors.dangerSoft,
          borderRadius: AppRadius.card,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              message,
              style: AppTextStyles.body.copyWith(color: AppColors.danger),
            ),
            if (onRetry != null)
              TextButton(
                key: const Key('assistant_retry'),
                onPressed: onRetry,
                child: const Text('Tekrar dene'),
              ),
          ],
        ),
      ),
    );
  }
}

/// Three dots that fade in turn while the answer is coming.
class TypingIndicator extends StatefulWidget {
  const TypingIndicator({super.key});

  @override
  State<TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<TypingIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1200),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Semantics(
        label: 'Asistan yazıyor',
        child: Container(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.l,
            vertical: AppSpacing.l,
          ),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: AppRadius.card,
            border: Border.all(color: AppColors.border),
          ),
          child: AnimatedBuilder(
            animation: _controller,
            builder: (context, _) => Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (var i = 0; i < 3; i++) ...[
                  if (i > 0) const SizedBox(width: AppSpacing.xxs),
                  Opacity(
                    opacity: _opacity(i),
                    child: Container(
                      width: AppSizes.typingDot,
                      height: AppSizes.typingDot,
                      decoration: const BoxDecoration(
                        color: AppColors.textMuted,
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// Each dot is brightest a third of the cycle after the previous one.
  double _opacity(int dot) {
    final phase = (_controller.value * 3 - dot) % 3;
    return phase < 1 ? 1 : 0.3;
  }
}
