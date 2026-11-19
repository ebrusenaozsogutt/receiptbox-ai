import 'package:flutter/services.dart';
import 'package:material_ui/material_ui.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_dimens.dart';
import '../../../../core/theme/app_text_styles.dart';
import '../../../../core/utils/date_format.dart';
import '../../../../core/utils/money_format.dart';
import '../../../../core/widgets/app_segmented.dart';
import '../../../transactions/domain/purchase_models.dart';
import '../../../transactions/domain/spending_category.dart';
import '../../domain/review_form.dart';
import 'review_widgets.dart';

/// The card with the purchase fields (Figma "Fields"): used by the receipt review screen and by
/// the manual / edit forms, so a purchase looks the same everywhere.
class FieldsCard extends StatelessWidget {
  const FieldsCard({
    super.key,
    required this.form,
    required this.onMerchant,
    required this.onDate,
    required this.onTime,
    required this.onTotal,
    required this.onCategory,
    required this.onChannel,
    this.onNote,
  });

  final ReviewForm form;
  final ValueChanged<String> onMerchant;
  final ValueChanged<DateTime> onDate;
  final ValueChanged<TimeOfDay?> onTime;
  final ValueChanged<int?> onTotal;
  final ValueChanged<SpendingCategory> onCategory;
  final ValueChanged<PurchaseChannel> onChannel;

  /// Only the manual and edit forms have a note field.
  final ValueChanged<String>? onNote;

  bool _flagged(ReviewField field) => form.flagged.contains(field);

  Future<void> _pickDate(BuildContext context) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: form.date,
      firstDate: DateTime(2000),
      lastDate: DateTime.now().add(const Duration(days: 1)),
      locale: const Locale('tr', 'TR'),
    );
    if (picked != null) onDate(picked);
  }

  Future<void> _pickTime(BuildContext context) async {
    final picked = await showTimePicker(
      context: context,
      initialTime: form.time ?? TimeOfDay.now(),
    );
    if (picked != null) onTime(picked);
  }

  Future<void> _pickCategory(BuildContext context) async {
    final picked = await pickCategory(context, form.category);
    if (picked != null) onCategory(picked);
  }

  @override
  Widget build(BuildContext context) {
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
          ReviewFieldBox(
            label: 'Mağaza',
            flagged: _flagged(ReviewField.merchant),
            validated: form.merchant.trim().isNotEmpty,
            checkKey: const Key('check_merchant'),
            child: BoxTextInput(
              key: const Key('field_merchant'),
              initialText: form.merchant,
              hint: 'Mağaza adı',
              onChanged: onMerchant,
            ),
          ),
          const SizedBox(height: AppSpacing.inputGap),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: ReviewFieldBox(
                  label: 'Tarih',
                  flagged: _flagged(ReviewField.date),
                  checkKey: const Key('check_date'),
                  onTap: () => _pickDate(context),
                  child: Text(
                    key: const Key('field_date'),
                    formatDateTr(form.date),
                    style: AppTextStyles.body,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.m),
              SizedBox(
                width: AppSizes.timeFieldWidth + AppSpacing.xxl,
                child: ReviewFieldBox(
                  label: 'Saat',
                  flagged: _flagged(ReviewField.time),
                  validated: form.time != null,
                  checkKey: const Key('check_time'),
                  onTap: () => _pickTime(context),
                  child: Text(
                    key: const Key('field_time'),
                    form.time == null ? '—' : timeLabel(form.time!),
                    style: AppTextStyles.body.copyWith(
                      color: form.time == null
                          ? AppColors.textSubtle
                          : AppColors.text,
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.inputGap),
          ReviewFieldBox(
            label: 'Toplam',
            flagged: _flagged(ReviewField.total),
            validated: form.totalMinor != null,
            checkKey: const Key('check_total'),
            child: BoxTextInput(
              key: const Key('field_total'),
              initialText: form.totalMinor == null
                  ? ''
                  : formatMoneyMinor(form.totalMinor!),
              hint: '0,00',
              suffix: 'TL',
              style: AppTextStyles.titleM,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              inputFormatters: [
                FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]')),
              ],
              onChanged: (text) => onTotal(parseMoneyToMinor(text)),
            ),
          ),
          const SizedBox(height: AppSpacing.inputGap),
          ReviewFieldBox(
            label: 'Kategori',
            flagged: _flagged(ReviewField.category),
            onTap: () => _pickCategory(context),
            trailing: const Icon(
              Icons.expand_more,
              size: AppSizes.icon,
              color: AppColors.textMuted,
            ),
            child: Row(
              key: const Key('field_category'),
              children: [
                CategoryDot(color: form.category.color),
                const SizedBox(width: AppSpacing.s),
                Expanded(
                  child: Text(
                    form.category.label,
                    style: AppTextStyles.body,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.inputGap),
          Text(
            'Nereden alındı?',
            style: AppTextStyles.label.copyWith(color: AppColors.textMuted),
          ),
          const SizedBox(height: AppSpacing.xs),
          AppSegmented<PurchaseChannel>(
            key: const Key('field_channel'),
            segments: const [
              Segment(PurchaseChannel.inStore, 'Mağazada'),
              Segment(PurchaseChannel.online, 'Online'),
            ],
            selected: form.channel,
            onChanged: onChannel,
          ),
          if (onNote != null) ...[
            const SizedBox(height: AppSpacing.inputGap),
            ReviewFieldBox(
              label: 'Not (isteğe bağlı)',
              flagged: false,
              validated: false,
              child: BoxTextInput(
                key: const Key('field_note'),
                initialText: form.note,
                hint: 'Not ekle',
                onChanged: onNote!,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
