import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/networking/api_error.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/utils/date_format.dart';
import '../../../core/utils/money_format.dart';
import '../../../core/widgets/app_segmented.dart';
import '../../../core/widgets/loading_view.dart';
import '../../../core/widgets/message_banner.dart';
import '../../transactions/domain/purchase_models.dart';
import '../../transactions/domain/spending_category.dart';
import '../data/products_api.dart';
import '../data/products_providers.dart';
import '../domain/product_models.dart';

/// "Ürün Ekle" (a product by hand) and "Düzenle" ([productId] set). A product by hand gets the
/// 2-year warranty suggestion when its date is known, and 14 days to return only when it was
/// bought online.
class AddProductScreen extends ConsumerWidget {
  const AddProductScreen({super.key, this.productId});

  final String? productId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final id = productId;
    if (id == null) return const _ProductForm(initial: null);
    final product = ref.watch(productDetailProvider(id));
    return product.when(
      loading: () => const Scaffold(body: LoadingView()),
      error: (_, _) => const Scaffold(body: LoadingView()),
      data: (data) => _ProductForm(initial: data),
    );
  }
}

class _ProductForm extends ConsumerStatefulWidget {
  const _ProductForm({required this.initial});

  final Product? initial;

  @override
  ConsumerState<_ProductForm> createState() => _ProductFormState();
}

class _ProductFormState extends ConsumerState<_ProductForm> {
  late final _name = TextEditingController(text: widget.initial?.name ?? '');
  late final _brand = TextEditingController(text: widget.initial?.brand ?? '');
  late final _model = TextEditingController(text: widget.initial?.model ?? '');
  late final _serial = TextEditingController(
    text: widget.initial?.serialNumber ?? '',
  );
  late final _price = TextEditingController(
    text: widget.initial?.priceMinor == null
        ? ''
        : formatMoneyMinor(widget.initial!.priceMinor!),
  );
  late SpendingCategory? _category = widget.initial?.category;
  late DateTime? _date = widget.initial?.purchaseDate;
  var _channel = PurchaseChannel.inStore;
  var _busy = false;
  String? _problem;

  bool get _editing => widget.initial != null;

  @override
  void dispose() {
    for (final c in [_name, _brand, _model, _serial, _price]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _date ?? DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime.now(),
      locale: const Locale('tr', 'TR'),
    );
    if (picked != null) setState(() => _date = picked);
  }

  Future<void> _save() async {
    final price = _price.text.trim().isEmpty
        ? null
        : parseMoneyToMinor(_price.text);
    if (_price.text.trim().isNotEmpty && price == null) {
      setState(() => _problem = 'Fiyat geçerli değil.');
      return;
    }
    setState(() {
      _busy = true;
      _problem = null;
    });
    final api = ref.read(productsApiProvider);
    final router = GoRouter.of(context);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final Product saved;
      if (_editing) {
        saved = await api.patch(widget.initial!.id, {
          'name': _name.text.trim(),
          'brand': _brand.text.trim().isEmpty ? null : _brand.text.trim(),
          'model': _model.text.trim().isEmpty ? null : _model.text.trim(),
          'serial_number': _serial.text.trim().isEmpty
              ? null
              : _serial.text.trim(),
          'category_key': _category?.key,
          'purchase_date': _date == null ? null : dateToApi(_date!),
          'purchase_price_minor': price,
        });
        ref.invalidate(productDetailProvider(saved.id));
      } else {
        saved = await api.create(
          ProductInput(
            name: _name.text,
            brand: _brand.text,
            model: _model.text,
            serialNumber: _serial.text,
            category: _category,
            purchaseDate: _date,
            priceMinor: price,
            channel: _channel,
          ),
        );
      }
      ref.invalidate(productListProvider);
      messenger.showSnackBar(
        SnackBar(
          content: Text(_editing ? 'Ürün güncellendi.' : 'Ürün eklendi.'),
        ),
      );
      if (_editing) {
        router.pop();
      } else {
        router.pushReplacement('/products/${saved.id}');
      }
    } on ApiError catch (error) {
      if (mounted) {
        setState(() {
          _busy = false;
          _problem = error.message;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final valid = _name.text.trim().isNotEmpty && !_busy;
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(title: Text(_editing ? 'Ürünü düzenle' : 'Ürün Ekle')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(AppSpacing.screenH),
          children: [
            TextField(
              key: const Key('product_name'),
              controller: _name,
              decoration: const InputDecoration(labelText: 'Ürün adı'),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: AppSpacing.inputGap),
            DropdownButtonFormField<SpendingCategory>(
              key: const Key('product_category'),
              initialValue: _category,
              decoration: const InputDecoration(labelText: 'Kategori'),
              items: [
                for (final c in SpendingCategory.values)
                  DropdownMenuItem(value: c, child: Text(c.label)),
              ],
              onChanged: (c) => setState(() => _category = c),
            ),
            const SizedBox(height: AppSpacing.inputGap),
            InkWell(
              key: const Key('product_date'),
              onTap: _pickDate,
              child: InputDecorator(
                decoration: const InputDecoration(labelText: 'Alış tarihi'),
                child: Text(
                  _date == null ? 'Seç' : formatDateTr(_date!),
                  style: AppTextStyles.body,
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.inputGap),
            TextField(
              key: const Key('product_price'),
              controller: _price,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: const InputDecoration(
                labelText: 'Fiyat (isteğe bağlı)',
                suffixText: 'TL',
              ),
            ),
            const SizedBox(height: AppSpacing.inputGap),
            TextField(
              key: const Key('product_brand'),
              controller: _brand,
              decoration: const InputDecoration(
                labelText: 'Marka (isteğe bağlı)',
              ),
            ),
            const SizedBox(height: AppSpacing.inputGap),
            TextField(
              key: const Key('product_model'),
              controller: _model,
              decoration: const InputDecoration(
                labelText: 'Model (isteğe bağlı)',
              ),
            ),
            const SizedBox(height: AppSpacing.inputGap),
            TextField(
              key: const Key('product_serial'),
              controller: _serial,
              decoration: const InputDecoration(
                labelText: 'Seri no (isteğe bağlı)',
              ),
            ),
            if (!_editing) ...[
              const SizedBox(height: AppSpacing.inputGap),
              Text(
                'Nereden alındı?',
                style: AppTextStyles.label.copyWith(color: AppColors.textMuted),
              ),
              const SizedBox(height: AppSpacing.xs),
              AppSegmented<PurchaseChannel>(
                key: const Key('product_channel'),
                segments: const [
                  Segment(PurchaseChannel.inStore, 'Mağazada'),
                  Segment(PurchaseChannel.online, 'Online'),
                ],
                selected: _channel,
                onChanged: (c) => setState(() => _channel = c),
              ),
            ],
            if (_problem != null) ...[
              const SizedBox(height: AppSpacing.m),
              MessageBanner(_problem!),
            ],
            const SizedBox(height: AppSpacing.xl),
            FilledButton(
              key: const Key('product_save'),
              onPressed: valid ? _save : null,
              child: const Text('Kaydet'),
            ),
          ],
        ),
      ),
    );
  }
}
