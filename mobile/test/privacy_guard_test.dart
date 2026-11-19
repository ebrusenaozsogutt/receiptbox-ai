import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Privacy rules of P04 as a test (spec 15.1, CLAUDE.md "No raw PII"):
/// the code that touches OCR text and images must not log anything and must not talk to
/// the network. Text read from a receipt can then only travel where the code explicitly
/// sends it, and in P04 nothing sends it.
const _guardedFolders = [
  'lib/core/ocr',
  'lib/core/privacy',
  'lib/features/capture',
];

const _extractionApiFile = 'features/capture/data/extraction_api.dart';

final _loggingCalls = RegExp(
  r'\bprint\s*\(|\bdebugPrint\s*\(|\bdeveloper\.log\s*\(|\blog\s*\(|\bdebugger\s*\(|stdout\.|stderr\.|FlutterError\.reportError',
);

final _networkImports = RegExp(
  r'''import\s+['"]package:(dio|http|web_socket_channel|firebase_[a-z_]+)/|import\s+['"]dart:(io\s+show\s+(HttpClient|Socket)|html)''',
);

Iterable<File> _dartFilesIn(String folder) => Directory(folder)
    .listSync(recursive: true)
    .whereType<File>()
    .where(
      (file) => file.path.endsWith('.dart') && !file.path.endsWith('.g.dart'),
    );

String _withoutComments(String source) => source
    .replaceAll(RegExp(r'/\*[\s\S]*?\*/'), '')
    .split('\n')
    .map((line) {
      final index = line.indexOf('//');
      return index >= 0 ? line.substring(0, index) : line;
    })
    .join('\n');

void main() {
  test('OCR, masking and capture code never log', () {
    final violations = <String>[];
    for (final folder in _guardedFolders) {
      for (final file in _dartFilesIn(folder)) {
        final lines = _withoutComments(file.readAsStringSync()).split('\n');
        for (var i = 0; i < lines.length; i++) {
          if (_loggingCalls.hasMatch(lines[i])) {
            violations.add('${file.path}:${i + 1}  ${lines[i].trim()}');
          }
        }
      }
    }
    expect(violations, isEmpty, reason: violations.join('\n'));
  });

  test(
    'OCR, masking and capture code do not use the network (one exception)',
    () {
      final violations = <String>[];
      for (final folder in _guardedFolders) {
        for (final file in _dartFilesIn(folder)) {
          // The ONE place that sends something: masked text / the cleaned QR to the backend
          // (P05/P06). The next test checks that it cannot send the original text.
          if (file.path.replaceAll(r'\', '/').endsWith(_extractionApiFile)) {
            continue;
          }
          final lines = _withoutComments(file.readAsStringSync()).split('\n');
          for (var i = 0; i < lines.length; i++) {
            if (_networkImports.hasMatch(lines[i])) {
              violations.add('${file.path}:${i + 1}  ${lines[i].trim()}');
            }
          }
        }
      }
      expect(violations, isEmpty, reason: violations.join('\n'));
    },
  );

  test('only the pipeline, the payload and the result screen ever touch the original text', () {
    // `debugOriginalText` is the unmasked OCR text (debug builds only). Anything that sends data
    // (extraction_api.dart) or shows server results must never reference it.
    const allowed = {
      'lib/features/capture/data/capture_pipeline.dart',
      'lib/features/capture/domain/capture_payload.dart',
      'lib/features/capture/presentation/capture_result_screen.dart',
    };
    final users = <String>[];
    for (final entity in Directory('lib').listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final path = entity.path.replaceAll(r'\', '/');
      if (entity.readAsStringSync().contains('debugOriginalText') &&
          !allowed.contains(path)) {
        users.add(path);
      }
    }
    expect(users, isEmpty, reason: users.join('\n'));
  });

  test('extraction_api.dart sends only the masked text and the cleaned QR', () {
    final source = File('lib/$_extractionApiFile').readAsStringSync();
    expect(source, contains('payload.maskedText'));
    expect(source, isNot(contains('debugOriginalText')));
    expect(source, isNot(contains('File(')));
  });

  test('the guarded folders exist (so the guards above are not vacuous)', () {
    for (final folder in _guardedFolders) {
      expect(_dartFilesIn(folder), isNotEmpty, reason: folder);
    }
  });

  test('the unmasked OCR text is only kept in debug builds', () {
    final pipeline = File('lib/features/capture/data/capture_pipeline.dart')
        .readAsStringSync();
    expect(
      pipeline,
      contains('debugOriginalText: keepOriginalForDebug ? original : null'),
    );
    expect(pipeline, contains('keepOriginalForDebug ?? kDebugMode'));
  });
}
