/// Recognises the QR code of a Turkish e-Archive / e-Invoice (GİB) and cleans it (spec 5.1).
///
/// The code holds a JSON object with keys such as `vkntckn`, `avkntckn`, `senaryo`, `tip`,
/// `tarih`, `no`, `ettn`, `parabirimi`, `malhizmettoplam`, `vergidahil`, `odenecek`.
///
/// PRIVACY: `avkntckn` is the BUYER's identity number (a person's TCKN). It is removed here,
/// on the phone, and the raw QR text is never kept: only the cleaned map leaves this function.
library;

import 'dart:convert';

class GibQrParser {
  const GibQrParser();

  /// Keys that mark a JSON object as a GİB invoice QR (any one is enough).
  static const _markerKeys = {'ettn', 'odenecek', 'vergidahil'};

  /// Keys that must never leave the device (compared in lower case).
  static const _privateKeys = {'avkntckn'};

  /// The cleaned payload of a GİB QR, or null when [raw] is anything else (a URL, a payment
  /// QR, a product barcode, broken JSON...). Unknown keys are kept; the backend ignores them.
  Map<String, dynamic>? parse(String raw) {
    final text = raw.replaceFirst('﻿', '').trim();
    if (!text.startsWith('{')) return null;

    final Object? decoded;
    try {
      decoded = jsonDecode(text);
    } on FormatException {
      return null;
    }
    if (decoded is! Map<String, dynamic>) return null;

    final lowerKeys = decoded.keys.map((key) => key.toLowerCase()).toSet();
    if (!lowerKeys.any(_markerKeys.contains)) return null;

    return {
      for (final entry in decoded.entries)
        if (!_privateKeys.contains(entry.key.toLowerCase()))
          entry.key: entry.value,
    };
  }

  /// The first GİB payload among the QR codes found in an image (there can be several codes).
  Map<String, dynamic>? firstGibPayload(Iterable<String> rawValues) {
    for (final raw in rawValues) {
      final payload = parse(raw);
      if (payload != null) return payload;
    }
    return null;
  }
}
