import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/storage/settings_store.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/widgets/screen_header.dart';
import '../domain/assistant_models.dart';
import 'assistant_actions.dart';
import 'assistant_controller.dart';
import 'assistant_widgets.dart';

/// The Asistan tab (P14): Turkish questions about the user's own purchases, answered only from
/// their records, with buttons that open the screen where each number can be checked. No Figma
/// frame: built from the theme tokens.
class AssistantScreen extends ConsumerStatefulWidget {
  const AssistantScreen({super.key});

  @override
  ConsumerState<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends ConsumerState<AssistantScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _ask(String text) {
    if (text.trim().isEmpty) return;
    _input.clear();
    FocusScope.of(context).unfocus();
    ref.read(assistantChatProvider.notifier).ask(text);
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
  }

  Future<void> _clear() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Geçmiş silinsin mi?'),
        content: const Text(
          'Sorduğun sorular ve cevaplar bu ekrandan ve sunucudan silinir.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Vazgeç'),
          ),
          TextButton(
            key: const Key('assistant_clear_confirm'),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Sil'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    final cleared = await ref.read(assistantChatProvider.notifier).clear();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          cleared ? 'Geçmiş silindi.' : 'Geçmiş silinemedi. Tekrar dene.',
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final consent = ref.watch(aiConsentProvider);
    final exchanges = ref.watch(assistantChatProvider);
    ref.listen(assistantChatProvider, (previous, next) => _scrollToEnd());
    final busy = exchanges.any((e) => e.pending);

    return SafeArea(
      child: Column(
        children: [
          ScreenHeader(
            title: 'Asistan',
            actions: [
              if (consent && exchanges.isNotEmpty)
                IconButton(
                  key: const Key('assistant_clear'),
                  tooltip: 'Geçmişi temizle',
                  onPressed: busy ? null : _clear,
                  icon: const Icon(Icons.delete_sweep_outlined),
                ),
            ],
          ),
          Expanded(
            child: !consent
                ? const _ConsentOff()
                : exchanges.isEmpty
                ? _Intro(onAsk: _ask)
                : _Conversation(exchanges: exchanges, controller: _scroll),
          ),
          if (consent) _Composer(controller: _input, busy: busy, onSend: _ask),
        ],
      ),
    );
  }
}

class _ConsentOff extends StatelessWidget {
  const _ConsentOff();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.xxl),
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            maxWidth: AppSizes.emptyStateMaxWidth,
          ),
          child: Column(
            key: const Key('assistant_consent_off'),
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.lock_outline,
                size: AppSizes.iconXl,
                color: AppColors.textSubtle,
              ),
              const SizedBox(height: AppSpacing.l),
              Text(
                'Asistan kapalı',
                style: AppTextStyles.titleM,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: AppSpacing.s),
              Text(
                'Asistan sorunu ve cevap için gereken kayıtlarını (tutarlar, mağaza ve '
                'ürün adları) yapay zekâ sağlayıcısına gönderir. Bunun için yapay zekâ '
                'iznini açman gerekiyor.',
                style: AppTextStyles.body.copyWith(color: AppColors.textMuted),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: AppSpacing.xxl),
              FilledButton(
                key: const Key('assistant_open_settings'),
                onPressed: () => context.push('/settings'),
                child: const Text("Ayarlar'a git"),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Intro extends StatelessWidget {
  const _Intro({required this.onAsk});

  final void Function(String question) onAsk;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.screenH),
      children: [
        const Icon(
          Icons.auto_awesome_outlined,
          size: AppSizes.iconXl,
          color: AppColors.primary,
        ),
        const SizedBox(height: AppSpacing.l),
        Text(
          'Alışverişlerine soru sor',
          style: AppTextStyles.titleM,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: AppSpacing.s),
        Text(
          'Cevaplar yalnızca kendi kayıtlarından gelir. Sayıları, cevabın altındaki '
          'düğmelerle ilgili ekranda kontrol edebilirsin.',
          style: AppTextStyles.body.copyWith(color: AppColors.textMuted),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: AppSpacing.xxl),
        Wrap(
          alignment: WrapAlignment.center,
          spacing: AppSpacing.s,
          runSpacing: AppSpacing.s,
          children: [
            for (var i = 0; i < suggestedQuestions.length; i++)
              ActionChip(
                key: Key('assistant_chip_$i'),
                label: Text(suggestedQuestions[i]),
                onPressed: () => onAsk(suggestedQuestions[i]),
              ),
          ],
        ),
      ],
    );
  }
}

class _Conversation extends ConsumerWidget {
  const _Conversation({required this.exchanges, required this.controller});

  final List<ChatExchange> exchanges;
  final ScrollController controller;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListView.builder(
      key: const Key('assistant_list'),
      controller: controller,
      padding: const EdgeInsets.all(AppSpacing.screenH),
      itemCount: exchanges.length,
      itemBuilder: (context, index) {
        final exchange = exchanges[index];
        final isLast = index == exchanges.length - 1;
        return Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.l),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              QuestionBubble(text: exchange.question),
              const SizedBox(height: AppSpacing.s),
              if (exchange.pending)
                const TypingIndicator(key: Key('assistant_typing'))
              else if (exchange.reply != null)
                AnswerBubble(
                  reply: exchange.reply!,
                  onAction: (action) =>
                      openAssistantAction(context, ref, action),
                )
              else
                ErrorBubble(
                  message: exchange.error!,
                  onRetry: isLast
                      ? () => ref.read(assistantChatProvider.notifier).retry()
                      : null,
                ),
            ],
          ),
        );
      },
    );
  }
}

class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.busy,
    required this.onSend,
  });

  final TextEditingController controller;
  final bool busy;
  final void Function(String text) onSend;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.screenH,
        AppSpacing.s,
        AppSpacing.s,
        AppSpacing.s,
      ),
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              key: const Key('assistant_input'),
              controller: controller,
              enabled: !busy,
              maxLength: 500,
              minLines: 1,
              maxLines: 4,
              textInputAction: TextInputAction.send,
              onSubmitted: onSend,
              decoration: const InputDecoration(
                hintText: 'Bir soru sor…',
                counterText: '',
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.s),
          IconButton.filled(
            key: const Key('assistant_send'),
            tooltip: 'Gönder',
            onPressed: busy ? null : () => onSend(controller.text),
            icon: const Icon(Icons.send),
          ),
        ],
      ),
    );
  }
}
