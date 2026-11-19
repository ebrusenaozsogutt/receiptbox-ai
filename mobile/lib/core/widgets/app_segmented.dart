import 'package:material_ui/material_ui.dart';

import '../theme/app_colors.dart';
import '../theme/app_dimens.dart';
import '../theme/app_text_styles.dart';

/// One option of an [AppSegmented].
class Segment<T> {
  const Segment(this.value, this.label);

  final T value;
  final String label;
}

/// The segmented control of Figma "02 · Fiş Kontrol" ("Mağazada | Online"): a grey track, the
/// selected segment white with a soft shadow.
class AppSegmented<T> extends StatelessWidget {
  const AppSegmented({
    super.key,
    required this.segments,
    required this.selected,
    required this.onChanged,
  });

  final List<Segment<T>> segments;
  final T selected;
  final ValueChanged<T> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.xxs),
      decoration: BoxDecoration(
        color: AppColors.surfaceAlt,
        borderRadius: AppRadius.control,
      ),
      child: Row(
        children: [
          for (var i = 0; i < segments.length; i++) ...[
            if (i > 0) const SizedBox(width: AppSpacing.xxs),
            Expanded(
              child: _SegmentButton(
                label: segments[i].label,
                selected: segments[i].value == selected,
                onTap: () => onChanged(segments[i].value),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _SegmentButton extends StatelessWidget {
  const _SegmentButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          height: AppSizes.segmentedHeight,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: selected ? AppColors.surface : null,
            borderRadius: AppRadius.circular(AppRadius.segment),
            boxShadow: selected ? AppShadows.segment : null,
          ),
          child: ExcludeSemantics(
            child: Text(
              label,
              style: AppTextStyles.label.copyWith(
                color: selected ? AppColors.text : AppColors.textMuted,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
