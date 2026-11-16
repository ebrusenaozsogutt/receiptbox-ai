import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Design rule: colors, font sizes/weights, spacing, radii and component sizes are defined ONLY
/// in lib/core/theme/. Everywhere else the code must use the tokens (AppColors, AppSpacing,
/// AppRadius, AppSizes, AppTextStyles). This test fails when a hard-coded value sneaks in, so
/// the design can still be changed in one place.
void main() {
  test('no hard-coded colors or sizes outside lib/core/theme/', () {
    final violations = <String>[];

    for (final entity in Directory('lib').listSync(recursive: true)) {
      if (entity is! File) continue;
      final path = entity.path.replaceAll('\\', '/');
      if (!path.endsWith('.dart') || path.endsWith('.g.dart')) continue;
      if (path.contains('/core/theme/')) continue;

      final content = _withoutComments(entity.readAsStringSync());
      final lines = content.split('\n');

      for (var i = 0; i < lines.length; i++) {
        final line = lines[i];
        for (final rule in _lineRules.entries) {
          if (rule.value.hasMatch(line)) {
            violations.add('$path:${i + 1}  [${rule.key}]  ${line.trim()}');
          }
        }
      }

      // Number literals inside EdgeInsets.xxx(...) argument lists, which can span several
      // lines. (SizedBox/Container sizes are caught by the line rules above.)
      var from = 0;
      while (true) {
        final start = content.indexOf('EdgeInsets.', from);
        if (start < 0) break;
        from = start + 'EdgeInsets.'.length;
        final args = _argumentsAt(content, content.indexOf('(', start));
        if (args != null && _numberLiteral.hasMatch(args)) {
          final line = content.substring(0, start).split('\n').length;
          violations.add(
            '$path:$line  [number in EdgeInsets]  ${args.replaceAll(RegExp(r"\s+"), " ")}',
          );
        }
      }
    }

    expect(
      violations,
      isEmpty,
      reason:
          'Move these values into lib/core/theme/ (app_colors, app_dimens, app_text_styles):\n'
          '${violations.join('\n')}',
    );
  });
}

final _lineRules = <String, RegExp>{
  'hard-coded color': RegExp(r'Color\(\s*0x|Color\.from|\bColors\.'),
  'font properties': RegExp(
    r'fontSize\s*:|fontWeight\s*:|fontFamily\s*:|FontWeight\.|letterSpacing\s*:',
  ),
  'own TextStyle': RegExp(r'\bTextStyle\('),
  'number radius': RegExp(r'Radius\.circular\(\s*[0-9]'),
  'number size': RegExp(
    r'\b(width|height|size|dimension|elevation|thickness|strokeWidth|radius|minWidth|minHeight|maxWidth|maxHeight|blurRadius)\s*:\s*[0-9]',
  ),
};

/// A digit that is a number literal (not part of an identifier such as `x2`).
final _numberLiteral = RegExp(r'(?<![A-Za-z_0-9.])[0-9]');

String _withoutComments(String source) {
  return source
      .replaceAll(RegExp(r'/\*[\s\S]*?\*/'), '')
      .split('\n')
      .map((line) {
        final index = line.indexOf('//');
        // Keep "http://" inside strings: only strip when the "//" is not preceded by ':'.
        if (index > 0 && line[index - 1] == ':') return line;
        return index >= 0 ? line.substring(0, index) : line;
      })
      .join('\n');
}

/// The text between the parentheses that open at [openIndex], or null if unbalanced.
String? _argumentsAt(String content, int openIndex) {
  if (openIndex < 0 ||
      openIndex >= content.length ||
      content[openIndex] != '(') {
    return null;
  }
  var depth = 0;
  for (var i = openIndex; i < content.length; i++) {
    if (content[i] == '(') depth++;
    if (content[i] == ')') {
      depth--;
      if (depth == 0) return content.substring(openIndex + 1, i);
    }
  }
  return null;
}
