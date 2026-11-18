/// Turns the text lines found by OCR (each with its position) into text in reading order.
///
/// ML Kit often returns "SÜT 1L" and "69,90" as two separate blocks. Printed on a receipt they
/// are one row, and the extraction step (P05) needs them together. So lines that sit on the same
/// horizontal band are joined (left to right, separated by two spaces), rows are ordered top to
/// bottom, and a larger vertical gap between rows becomes an empty line (a new paragraph).
/// Pure Dart, no ML Kit types, so it is easy to test.
library;

class OcrLine {
  const OcrLine({
    required this.text,
    required this.left,
    required this.top,
    required this.right,
    required this.bottom,
  });

  final String text;
  final double left;
  final double top;
  final double right;
  final double bottom;

  double get height => bottom - top;
  double get centerY => (top + bottom) / 2;
}

class ReadingOrder {
  const ReadingOrder();

  /// A gap between two rows larger than this many line heights starts a new paragraph.
  static const _paragraphGapInLineHeights = 0.9;

  /// Two lines are on the same row when they overlap vertically by at least this share of
  /// the smaller one.
  static const _sameRowOverlap = 0.5;

  String arrange(List<OcrLine> lines) {
    final usable = lines.where((line) => line.text.trim().isNotEmpty).toList();
    if (usable.isEmpty) return '';
    usable.sort((a, b) {
      final byY = a.centerY.compareTo(b.centerY);
      return byY != 0 ? byY : a.left.compareTo(b.left);
    });

    final rows = <_Row>[];
    for (final line in usable) {
      if (rows.isNotEmpty && rows.last.accepts(line, _sameRowOverlap)) {
        rows.last.add(line);
      } else {
        rows.add(_Row(line));
      }
    }

    final heights = rows.map((row) => row.height).toList()..sort();
    final medianHeight = heights[heights.length ~/ 2];

    final out = StringBuffer();
    for (var i = 0; i < rows.length; i++) {
      if (i > 0) {
        final gap = rows[i].top - rows[i - 1].bottom;
        out.write(
          gap > medianHeight * _paragraphGapInLineHeights ? '\n\n' : '\n',
        );
      }
      out.write(rows[i].text);
    }
    return out.toString();
  }
}

class _Row {
  _Row(OcrLine first)
    : _lines = [first],
      top = first.top,
      bottom = first.bottom;

  final List<OcrLine> _lines;
  double top;
  double bottom;

  double get height => bottom - top;

  bool accepts(OcrLine line, double minOverlapShare) {
    final overlap =
        (line.bottom < bottom ? line.bottom : bottom) -
        (line.top > top ? line.top : top);
    final smaller = line.height < height ? line.height : height;
    return smaller > 0 && overlap / smaller >= minOverlapShare;
  }

  void add(OcrLine line) {
    _lines.add(line);
    if (line.top < top) top = line.top;
    if (line.bottom > bottom) bottom = line.bottom;
  }

  String get text {
    final ordered = [..._lines]..sort((a, b) => a.left.compareTo(b.left));
    return ordered.map((line) => line.text.trim()).join('  ');
  }
}
