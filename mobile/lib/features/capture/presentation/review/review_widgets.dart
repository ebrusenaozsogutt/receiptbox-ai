import 'dart:io';

import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_dimens.dart';
import '../../../../core/theme/app_text_styles.dart';
import '../../../../core/utils/money_format.dart';
import '../../../../core/widgets/review_badge.dart';
import '../../../transactions/domain/spending_category.dart';
import '../../domain/review_form.dart';

/// A labelled field box of the review screen (Figma "Field/..."): label above, a 48 high box with
/// the value, and at the end either a green check (read and validated), the "KONTROL ET" badge on
/// a warning background (the app is not sure), or nothing.
class ReviewFieldBox extends StatelessWidget {
  const ReviewFieldBox({
    super.key,
    required this.label,
    required this.child,
    required this.flagged,
    this.validated = true,
    this.trailing,
    this.onTap,
    this.checkKey,
  });

  final String label;
  final Widget child;
  final bool flagged;

  /// Show the green check (only when the field is not flagged).
  final bool validated;

  /// Shown instead of the check, for example a chevron.
  final Widget? trailing;
  final VoidCallback? onTap;
  final Key? checkKey;

  @override
  Widget build(BuildContext context) {
    final Widget end;
    if (flagged) {
      end = const ReviewBadge();
    } else if (trailing != null) {
      end = trailing!;
    } else if (validated) {
      end = Icon(
        Icons.check,
        key: checkKey,
        size: AppSizes.fieldCheck,
        color: AppColors.success,
      );
    } else {
      end = const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: AppTextStyles.label.copyWith(color: AppColors.textMuted),
        ),
        const SizedBox(height: AppSpacing.xs),
        InkWell(
          onTap: onTap,
          borderRadius: AppRadius.control,
          child: Container(
            constraints: const BoxConstraints(minHeight: AppSizes.inputHeight),
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.inputGap),
            decoration: BoxDecoration(
              color: flagged ? AppColors.warningSoft : AppColors.surface,
              borderRadius: AppRadius.control,
              border: Border.all(color: AppColors.border),
            ),
            child: Row(
              children: [
                Expanded(child: child),
                const SizedBox(width: AppSpacing.s),
                end,
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// A text input that lives inside a [ReviewFieldBox] (no border of its own).
class BoxTextInput extends StatefulWidget {
  const BoxTextInput({
    super.key,
    required this.initialText,
    required this.onChanged,
    this.style,
    this.keyboardType,
    this.hint,
    this.inputFormatters,
    this.suffix,
  });

  final String initialText;
  final ValueChanged<String> onChanged;
  final TextStyle? style;
  final TextInputType? keyboardType;
  final String? hint;
  final List<TextInputFormatter>? inputFormatters;
  final String? suffix;

  @override
  State<BoxTextInput> createState() => _BoxTextInputState();
}

class _BoxTextInputState extends State<BoxTextInput> {
  late final TextEditingController _controller = TextEditingController(
    text: widget.initialText,
  );

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: TextField(
            controller: _controller,
            onChanged: widget.onChanged,
            keyboardType: widget.keyboardType,
            inputFormatters: widget.inputFormatters,
            style: widget.style ?? AppTextStyles.body,
            // The box around it is drawn by ReviewFieldBox, so every border of the app-wide
            // input theme is switched off here.
            decoration: InputDecoration(
              isCollapsed: true,
              filled: false,
              border: InputBorder.none,
              enabledBorder: InputBorder.none,
              focusedBorder: InputBorder.none,
              disabledBorder: InputBorder.none,
              errorBorder: InputBorder.none,
              focusedErrorBorder: InputBorder.none,
              contentPadding: EdgeInsets.zero,
              hintText: widget.hint,
              hintStyle: AppTextStyles.body.copyWith(color: AppColors.textSubtle),
            ),
          ),
        ),
        if (widget.suffix != null)
          Text(
            widget.suffix!,
            style: (widget.style ?? AppTextStyles.body).copyWith(
              color: AppColors.textMuted,
            ),
          ),
      ],
    );
  }
}

/// The receipt card at the top (Figma "ReceiptPreview").
class ReceiptPreviewCard extends StatelessWidget {
  const ReceiptPreviewCard({
    super.key,
    required this.image,
    required this.isPdf,
    required this.isQr,
  });

  final File? image;
  final bool isPdf;
  final bool isQr;

  @override
  Widget build(BuildContext context) {
    final title = isPdf
        ? 'e-Fatura PDF'
        : image != null
        ? 'Fiş fotoğrafı'
        : isQr
        ? 'e-Fatura'
        : 'Fiş';
    final subtitle = image != null
        ? 'Cihazda okundu · kişisel bilgiler gizlendi'
        : 'Cihazda okundu · görsel saklanmayacak';
    final canExpand = image != null && !isPdf;

    return Container(
      padding: const EdgeInsets.all(AppSpacing.m),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.card,
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          ClipRRect(
            borderRadius: AppRadius.circular(AppRadius.thumbnail),
            child: Container(
              key: const Key('receipt_thumbnail'),
              width: AppSizes.receiptThumbWidth,
              height: AppSizes.receiptThumbHeight,
              color: AppColors.surfaceAlt,
              child: canExpand
                  ? Image.file(
                      image!,
                      fit: BoxFit.cover,
                      errorBuilder: (_, _, _) => _placeholder(),
                    )
                  : _placeholder(),
            ),
          ),
          const SizedBox(width: AppSpacing.inputGap),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: AppTextStyles.bodyStrong),
                Text(
                  subtitle,
                  style: AppTextStyles.bodyS.copyWith(
                    color: AppColors.textMuted,
                  ),
                ),
              ],
            ),
          ),
          if (canExpand)
            IconButton(
              key: const Key('receipt_expand'),
              tooltip: 'Büyüt',
              icon: const Icon(
                Icons.open_in_full,
                color: AppColors.primary,
                size: AppSizes.fieldCheck,
              ),
              onPressed: () => showDialog<void>(
                context: context,
                builder: (_) => FullImageDialog(file: image!),
              ),
            ),
        ],
      ),
    );
  }

  Widget _placeholder() => Icon(
    isPdf ? Icons.picture_as_pdf_outlined : Icons.receipt_long_outlined,
    color: AppColors.textSubtle,
    size: AppSizes.icon,
  );
}

class FullImageDialog extends StatelessWidget {
  const FullImageDialog({super.key, required this.file});

  final File file;

  @override
  Widget build(BuildContext context) {
    return Dialog.fullscreen(
      backgroundColor: AppColors.cameraBackground,
      child: Stack(
        children: [
          Positioned.fill(
            child: InteractiveViewer(child: Image.file(file)),
          ),
          SafeArea(
            child: Align(
              alignment: Alignment.topRight,
              child: IconButton(
                tooltip: 'Kapat',
                icon: const Icon(Icons.close, color: AppColors.cameraForeground),
                onPressed: () => Navigator.of(context).pop(),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// The banner under the receipt card: how many fields wait for a look, or that all are fine.
class ReviewBanner extends StatelessWidget {
  const ReviewBanner({super.key, required this.pending, this.notice});

  final int pending;

  /// Shown instead when the receipt could not be read at all.
  final String? notice;

  @override
  Widget build(BuildContext context) {
    final Color background;
    final Color foreground;
    final IconData icon;
    final String text;
    if (notice != null) {
      background = AppColors.infoSoft;
      foreground = AppColors.info;
      icon = Icons.info_outline;
      text = notice!;
    } else if (pending > 0) {
      background = AppColors.warningSoft;
      foreground = AppColors.warning;
      icon = Icons.warning_amber_rounded;
      text = '$pending alan kontrol bekliyor. Diğerleri fişte doğrulandı.';
    } else {
      background = AppColors.successSoft;
      foreground = AppColors.success;
      icon = Icons.check_circle_outline;
      text = 'Tüm alanlar fişte doğrulandı.';
    }
    return Semantics(
      liveRegion: true,
      child: Container(
        key: const Key('review_banner'),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.inputGap,
          vertical: AppSpacing.m,
        ),
        decoration: BoxDecoration(
          color: background,
          borderRadius: AppRadius.circular(AppRadius.banner),
        ),
        child: Row(
          children: [
            Icon(icon, size: AppSizes.icon - 4, color: foreground),
            const SizedBox(width: AppSpacing.s),
            Expanded(
              child: Text(
                text,
                style: AppTextStyles.bodyS.copyWith(color: AppColors.text),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The category list (13 options) as a bottom sheet. Returns the chosen category or null.
Future<SpendingCategory?> pickCategory(
  BuildContext context,
  SpendingCategory current,
) {
  return showModalBottomSheet<SpendingCategory>(
    context: context,
    useRootNavigator: true,
    isScrollControlled: true,
    builder: (sheetContext) => SafeArea(
      child: ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.screenH,
          AppSpacing.none,
          AppSpacing.screenH,
          AppSpacing.l,
        ),
        children: [
          Text('Kategori', style: AppTextStyles.titleM),
          const SizedBox(height: AppSpacing.s),
          for (final category in SpendingCategory.values)
            ListTile(
              key: Key('category_${category.key}'),
              contentPadding: EdgeInsets.zero,
              leading: CategoryDot(color: category.color),
              title: Text(category.label),
              trailing: category == current
                  ? const Icon(Icons.check, color: AppColors.primary)
                  : null,
              onTap: () => Navigator.of(sheetContext).pop(category),
            ),
        ],
      ),
    ),
  );
}

/// The answer of [pickCategoryFilter]: a category, or null for "Tümü" (no filter).
class CategoryChoice {
  const CategoryChoice(this.category);

  final SpendingCategory? category;
}

/// The same list with a first "Tümü" row, for the filter of the purchase list. Returns null
/// when the sheet is dismissed.
Future<CategoryChoice?> pickCategoryFilter(
  BuildContext context,
  SpendingCategory? current,
) {
  return showModalBottomSheet<CategoryChoice>(
    context: context,
    useRootNavigator: true,
    isScrollControlled: true,
    builder: (sheetContext) => SafeArea(
      child: ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.screenH,
          AppSpacing.none,
          AppSpacing.screenH,
          AppSpacing.l,
        ),
        children: [
          Text('Kategori', style: AppTextStyles.titleM),
          const SizedBox(height: AppSpacing.s),
          ListTile(
            key: const Key('category_all'),
            contentPadding: EdgeInsets.zero,
            title: const Text('Tümü'),
            trailing: current == null
                ? const Icon(Icons.check, color: AppColors.primary)
                : null,
            onTap: () => Navigator.of(sheetContext).pop(const CategoryChoice(null)),
          ),
          for (final category in SpendingCategory.values)
            ListTile(
              key: Key('category_${category.key}'),
              contentPadding: EdgeInsets.zero,
              leading: CategoryDot(color: category.color),
              title: Text(category.label),
              trailing: category == current
                  ? const Icon(Icons.check, color: AppColors.primary)
                  : null,
              onTap: () => Navigator.of(sheetContext).pop(CategoryChoice(category)),
            ),
        ],
      ),
    ),
  );
}

class CategoryDot extends StatelessWidget {
  const CategoryDot({super.key, required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: AppSizes.categoryDot,
      height: AppSizes.categoryDot,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );
  }
}

/// The items card (Figma "Items"): lines with amounts, "Düzenle", and whether they add up.
class ItemsCard extends StatefulWidget {
  const ItemsCard({
    super.key,
    required this.lines,
    required this.totalMinor,
    required this.flagged,
    required this.onChanged,
  });

  final List<EditableLine> lines;
  final int? totalMinor;
  final bool flagged;
  final ValueChanged<List<EditableLine>> onChanged;

  @override
  State<ItemsCard> createState() => _ItemsCardState();
}

class _ItemsCardState extends State<ItemsCard> {
  bool _editing = false;
  bool _expanded = true;

  void _replace(int index, EditableLine line) {
    final lines = [...widget.lines]..[index] = line;
    widget.onChanged(lines);
  }

  @override
  Widget build(BuildContext context) {
    final lines = widget.lines;
    return Container(
      padding: const EdgeInsets.all(AppSpacing.l),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: AppRadius.card,
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: InkWell(
                  key: const Key('items_toggle'),
                  onTap: () => setState(() => _expanded = !_expanded),
                  child: Row(
                    children: [
                      Text('Kalemler (${lines.length})', style: AppTextStyles.titleS),
                      const SizedBox(width: AppSpacing.xs),
                      Icon(
                        _expanded ? Icons.expand_less : Icons.expand_more,
                        size: AppSizes.icon,
                        color: AppColors.textMuted,
                      ),
                      if (widget.flagged) ...[
                        const SizedBox(width: AppSpacing.s),
                        const ReviewBadge(),
                      ],
                    ],
                  ),
                ),
              ),
              TextButton(
                key: const Key('items_edit'),
                onPressed: () => setState(() {
                  _editing = !_editing;
                  _expanded = true;
                }),
                child: Text(_editing ? 'Bitti' : 'Düzenle'),
              ),
            ],
          ),
          if (_expanded) ...[
            if (lines.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: AppSpacing.m),
                child: Text(
                  'Kalem okunamadı.',
                  style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
                ),
              ),
            for (var i = 0; i < lines.length; i++)
              _editing ? _editRow(i, lines[i]) : _readRow(lines[i]),
            if (_editing)
              TextButton.icon(
                key: const Key('items_add'),
                onPressed: () => widget.onChanged([
                  ...lines,
                  const EditableLine(name: ''),
                ]),
                icon: const Icon(Icons.add),
                label: const Text('Kalem ekle'),
              ),
            _sumCheck(),
          ],
        ],
      ),
    );
  }

  Widget _readRow(EditableLine line) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.rowV),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        children: [
          Expanded(child: Text(line.name, style: AppTextStyles.body)),
          if (line.totalMinor != null)
            Text(formatMoneyTl(line.totalMinor!), style: AppTextStyles.bodyStrong),
        ],
      ),
    );
  }

  Widget _editRow(int index, EditableLine line) {
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.s),
      child: Row(
        children: [
          Expanded(
            child: TextFormField(
              key: ValueKey('line_name_$index'),
              initialValue: line.name,
              style: AppTextStyles.body,
              decoration: const InputDecoration(hintText: 'Kalem adı'),
              onChanged: (value) => _replace(index, line.copyWith(name: value)),
            ),
          ),
          const SizedBox(width: AppSpacing.s),
          SizedBox(
            width: AppSizes.timeFieldWidth,
            child: TextFormField(
              key: ValueKey('line_total_$index'),
              initialValue: line.totalMinor == null
                  ? ''
                  : formatMoneyMinor(line.totalMinor!),
              style: AppTextStyles.body,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(hintText: 'Tutar'),
              onChanged: (value) => _replace(
                index,
                line.copyWith(totalMinor: () => parseMoneyToMinor(value)),
              ),
            ),
          ),
          IconButton(
            key: ValueKey('line_remove_$index'),
            tooltip: 'Kalemi sil',
            icon: const Icon(Icons.delete_outline, color: AppColors.danger),
            onPressed: () => widget.onChanged([...widget.lines]..removeAt(index)),
          ),
        ],
      ),
    );
  }

  Widget _sumCheck() {
    final check = itemsSumCheck(widget.lines, widget.totalMinor);
    if (check == SumCheck.none) return const SizedBox.shrink();
    final ok = check == SumCheck.matches;
    final text = switch (check) {
      SumCheck.matches => 'Kalemlerin toplamı fiş toplamıyla uyuşuyor',
      SumCheck.differs =>
        'Kalemlerin toplamı fiş toplamıyla uyuşmuyor '
            '(${_difference()} fark)',
      _ => 'Bazı kalemlerin tutarı yok; toplam kontrol edilemedi',
    };
    final color = ok ? AppColors.success : AppColors.warning;
    return Padding(
      key: const Key('items_sum_check'),
      padding: const EdgeInsets.only(top: AppSpacing.m),
      child: Row(
        children: [
          Icon(
            ok ? Icons.check : Icons.warning_amber_rounded,
            size: AppSizes.iconS - 2,
            color: color,
          ),
          const SizedBox(width: AppSpacing.s),
          Expanded(
            child: Text(text, style: AppTextStyles.bodyS.copyWith(color: color)),
          ),
        ],
      ),
    );
  }

  String _difference() {
    final sum = widget.lines.fold<int>(0, (s, l) => s + (l.totalMinor ?? 0));
    return formatMoneyTl((sum - widget.totalMinor!).abs());
  }
}
