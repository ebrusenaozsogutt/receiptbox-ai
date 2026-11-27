// P15 E4 (privacy): runs the app's own PII masker over synthetic texts.
//
//   dart run tool/mask_jsonl.dart <input.jsonl> <output.jsonl>
//
// Each input line: {"id": "...", "text": "...", "bank": false}. Each output line:
// {"id": "...", "masked": "...", "counts": {"iban": 1, ...}}. Only synthetic texts are fed in
// (ai/experiments/rbx_eval/e4.py); nothing is sent anywhere.
import 'dart:convert';
import 'dart:io';

import 'package:receiptbox/core/privacy/pii_masker.dart';

void main(List<String> args) {
  if (args.length != 2) {
    stderr.writeln('usage: dart run tool/mask_jsonl.dart <input.jsonl> <output.jsonl>');
    exit(64);
  }
  const masker = PiiMasker();
  final out = File(args[1]).openWrite();
  var n = 0;
  for (final line in File(args[0]).readAsLinesSync()) {
    if (line.trim().isEmpty) continue;
    final item = jsonDecode(line) as Map<String, dynamic>;
    final result = masker.mask(
      item['text'] as String,
      bank: item['bank'] as bool? ?? false,
    );
    out.writeln(
      jsonEncode({
        'id': item['id'],
        'masked': result.text,
        'counts': {
          for (final entry in result.counts.entries) entry.key.name: entry.value,
        },
      }),
    );
    n++;
  }
  out.close();
  stdout.writeln('masked $n texts');
}
