import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/utils/money_format.dart';
import '../data/products_api.dart';
import '../data/products_providers.dart';
import '../domain/product_models.dart';

enum SuggestionAnswer { track, never }

/// "Bunu ürün olarak takip edelim mi?" (spec 10.1): Evet / Hayır, bir daha sorma. Closing the
/// sheet answers nothing: the suggestion stays on the Products tab.
Future<SuggestionAnswer?> showProductSuggestionSheet(
  BuildContext context,
  ProductSuggestion suggestion,
) => showModalBottomSheet<SuggestionAnswer>(
  context: context,
  useRootNavigator: true,
  builder: (_) => ProductSuggestionSheet(suggestion: suggestion),
);

/// Asks, then does what the user chose. Returns the new product's id when one was made.
Future<String?> askToTrackProduct({
  required BuildContext context,
  required ProviderContainer container,
  required ProductSuggestion suggestion,
}) async {
  final messenger = ScaffoldMessenger.maybeOf(context);
  final answer = await showProductSuggestionSheet(context, suggestion);
  if (answer == null) return null;
  final api = container.read(productsApiProvider);
  try {
    if (answer == SuggestionAnswer.never) {
      await api.dismiss(suggestion);
      container.invalidate(productSuggestionsProvider);
      return null;
    }
    final product = await api.create(
      ProductInput(
        transactionId: suggestion.transactionId,
        receiptItemId: suggestion.receiptItemId,
      ),
    );
    container
      ..invalidate(productListProvider)
      ..invalidate(productSuggestionsProvider);
    return product.id;
  } on ApiError catch (error) {
    messenger?.showSnackBar(SnackBar(content: Text(error.message)));
    return null;
  }
}

class ProductSuggestionSheet extends StatelessWidget {
  const ProductSuggestionSheet({super.key, required this.suggestion});

  final ProductSuggestion suggestion;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        key: const Key('product_suggestion_sheet'),
        padding: const EdgeInsets.all(AppSpacing.screenH),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Bunu ürün olarak takip edelim mi?',
              style: AppTextStyles.titleM,
            ),
            const SizedBox(height: AppSpacing.s),
            Text(
              '${suggestion.name} · ${formatMoneyTl(suggestion.priceMinor)}',
              style: AppTextStyles.bodyStrong,
            ),
            const SizedBox(height: AppSpacing.xxs),
            Text(
              'Garantisini (yasal asgari 2 yıl) ve iade süresini senin için '
              'takip ederiz; tarihleri sonra düzenleyebilirsin.',
              style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
            ),
            const SizedBox(height: AppSpacing.l),
            FilledButton(
              key: const Key('track_yes'),
              onPressed: () =>
                  Navigator.of(context).pop(SuggestionAnswer.track),
              child: const Text('Evet'),
            ),
            const SizedBox(height: AppSpacing.s),
            TextButton(
              key: const Key('track_never'),
              onPressed: () =>
                  Navigator.of(context).pop(SuggestionAnswer.never),
              child: const Text('Hayır, bir daha sorma'),
            ),
          ],
        ),
      ),
    );
  }
}
