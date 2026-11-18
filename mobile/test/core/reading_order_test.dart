import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/core/ocr/reading_order.dart';

OcrLine line(
  String text,
  double left,
  double top, {
  double height = 20,
  double width = 100,
}) => OcrLine(
  text: text,
  left: left,
  top: top,
  right: left + width,
  bottom: top + height,
);

void main() {
  const order = ReadingOrder();

  test('empty input gives empty text', () {
    expect(order.arrange(const []), '');
    expect(order.arrange([line('   ', 0, 0)]), '');
  });

  test(
    'a name and its price on the same band become one row, left to right',
    () {
      final text = order.arrange([
        line('69,90', 300, 102),
        line('SÜT 1L', 10, 100),
      ]);
      expect(text, 'SÜT 1L  69,90');
    },
  );

  test(
    'rows are ordered top to bottom even when the engine returns them shuffled',
    () {
      final text = order.arrange([
        line('C', 10, 140),
        line('A', 10, 100),
        line('B', 10, 120),
      ]);
      expect(text, 'A\nB\nC');
    },
  );

  test('a large vertical gap starts a new paragraph', () {
    final text = order.arrange([
      line('MARKET A.Ş.', 10, 100),
      line('Fiş No: 12', 10, 122),
      line('TOPLAM', 10, 300),
      line('120,00', 200, 300),
    ]);
    expect(text, 'MARKET A.Ş.\nFiş No: 12\n\nTOPLAM  120,00');
  });

  test('lines that only touch the next row are not merged into it', () {
    final text = order.arrange([
      line('first', 10, 100, height: 20),
      line('second', 10, 121, height: 20),
    ]);
    expect(text, 'first\nsecond');
  });

  test('text is trimmed', () {
    expect(order.arrange([line('  ekmek  ', 0, 0)]), 'ekmek');
  });
}
