import 'package:material_ui/material_ui.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_dimens.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/utils/date_format.dart';
import '../../../core/utils/money_format.dart';
import '../../../core/widgets/app_segmented.dart';

/// What the user entered in the "İade edildi" dialog.
class RefundAnswer {
  const RefundAnswer({required this.amountMinor, required this.date});

  final int amountMinor;
  final DateTime date;
}

enum _Kind { full, partial }

/// "İade edildi": the whole remaining amount or a part of it, and the day of the refund (between
/// the purchase and today). Null when cancelled.
Future<RefundAnswer?> showRefundDialog(
  BuildContext context, {
  required int refundableMinor,
  required DateTime purchaseDate,
  required DateTime today,
}) => showDialog<RefundAnswer>(
  context: context,
  builder: (_) => _RefundDialog(
    refundableMinor: refundableMinor,
    purchaseDate: purchaseDate,
    today: today,
  ),
);

class _RefundDialog extends StatefulWidget {
  const _RefundDialog({
    required this.refundableMinor,
    required this.purchaseDate,
    required this.today,
  });

  final int refundableMinor;
  final DateTime purchaseDate;
  final DateTime today;

  @override
  State<_RefundDialog> createState() => _RefundDialogState();
}

class _RefundDialogState extends State<_RefundDialog> {
  final _amount = TextEditingController();
  var _kind = _Kind.full;
  late DateTime _date = widget.today;

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  int? get _value => _kind == _Kind.full
      ? widget.refundableMinor
      : parseMoneyToMinor(_amount.text);

  String? get _problem {
    final value = _value;
    if (_kind == _Kind.partial && _amount.text.trim().isEmpty) return null;
    if (value == null || value <= 0) return 'Geçerli bir tutar gir.';
    if (value > widget.refundableMinor) {
      return 'En fazla ${formatMoneyTl(widget.refundableMinor)} iade edilebilir.';
    }
    return null;
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: widget.purchaseDate,
      lastDate: widget.today,
      locale: const Locale('tr', 'TR'),
    );
    if (picked != null) setState(() => _date = picked);
  }

  @override
  Widget build(BuildContext context) {
    final value = _value;
    final valid = _problem == null && value != null && value > 0;
    return AlertDialog(
      title: const Text('İade edildi'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AppSegmented<_Kind>(
            key: const Key('refund_kind'),
            segments: const [
              Segment(_Kind.full, 'Tamamı'),
              Segment(_Kind.partial, 'Bir kısmı'),
            ],
            selected: _kind,
            onChanged: (kind) => setState(() => _kind = kind),
          ),
          const SizedBox(height: AppSpacing.m),
          if (_kind == _Kind.full)
            Text(
              formatMoneyTl(widget.refundableMinor),
              key: const Key('refund_full_amount'),
              style: AppTextStyles.titleM,
            )
          else
            TextField(
              key: const Key('refund_amount'),
              controller: _amount,
              autofocus: true,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: InputDecoration(
                labelText: 'İade tutarı',
                suffixText: 'TL',
                errorText: _problem,
              ),
              onChanged: (_) => setState(() {}),
            ),
          const SizedBox(height: AppSpacing.m),
          InkWell(
            key: const Key('refund_date'),
            onTap: _pickDate,
            child: Row(
              children: [
                const Icon(Icons.event_outlined, size: AppSizes.iconS),
                const SizedBox(width: AppSpacing.s),
                Text(formatDateTr(_date), style: AppTextStyles.body),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.s),
          Text(
            'Harcama, alışverişin yapıldığı ayda bu tutar kadar azalır.',
            style: AppTextStyles.bodyS.copyWith(color: AppColors.textMuted),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Vazgeç'),
        ),
        TextButton(
          key: const Key('refund_save'),
          onPressed: valid
              ? () =>
                    Navigator.of(context)
                        .pop(RefundAnswer(amountMinor: value, date: _date))
              : null,
          child: const Text('Kaydet'),
        ),
      ],
    );
  }
}
