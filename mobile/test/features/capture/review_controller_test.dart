import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:receiptbox/core/privacy/pii_masker.dart';
import 'package:receiptbox/core/storage/settings_store.dart';
import 'package:receiptbox/features/capture/data/capture_providers.dart';
import 'package:receiptbox/features/capture/domain/capture_payload.dart';
import 'package:receiptbox/features/capture/domain/extraction_result.dart';
import 'package:receiptbox/features/capture/presentation/review/review_controller.dart';
import 'package:receiptbox/features/matching/domain/match_models.dart';
import 'package:receiptbox/features/transactions/data/transactions_api.dart';
import 'package:receiptbox/features/transactions/domain/purchase_models.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/fakes.dart';
import '../../support/purchase_fakes.dart';

MatchSuggestion _suggestion() => MatchSuggestion(
  id: 'd-1',
  score: 90,
  observation: MatchObservation(
    id: 'obs-1',
    source: EvidenceKind.receipt,
    merchant: 'Migros',
    date: DateTime(2026, 11, 14),
    time: null,
    totalMinor: 27030,
  ),
  transaction: MatchTransaction(
    id: 'tx-9',
    merchant: 'Migros',
    category: null,
    date: DateTime(2026, 11, 14),
    time: null,
    totalMinor: 27030,
    sources: const [EvidenceKind.bank],
  ),
);

/// The review controller with real files (the kept receipt image) and fake APIs.
void main() {
  late Directory root;
  late FakeTransactionsApi transactions;
  late FakeDocumentsApi documents;
  late FakeExtractionApi extraction;
  late ProviderContainer container;

  setUp(() async {
    root = await Directory.systemTemp.createTemp('review_controller_test');
    SharedPreferences.setMockInitialValues({'ai_consent': true});
    transactions = FakeTransactionsApi();
    documents = FakeDocumentsApi();
    extraction = FakeExtractionApi()
      ..result = const ExtractionResult(
        observationId: 'obs-1',
        merchant: 'MIGROS',
        date: '2026-11-14',
        total: '270.30',
        itemCount: 0,
        confidence: {'merchant': 'HIGH', 'date': 'HIGH', 'total': 'HIGH'},
        merchantMatch: 'GLOBAL_ALIAS',
        merchantName: 'Migros',
        categoryKey: 'GROCERY',
        categorySource: 'MERCHANT_DEFAULT',
        aiUsed: true,
        usedQr: false,
        totalMinor: 27030,
      );
    container = ProviderContainer(
      overrides: [
        sharedPreferencesProvider.overrideWithValue(
          await SharedPreferences.getInstance(),
        ),
        transactionsApiProvider.overrideWithValue(transactions),
        documentsApiProvider.overrideWithValue(documents),
        extractionApiProvider.overrideWithValue(extraction),
      ],
    );
    addTearDown(container.dispose);
    // Keep the auto-dispose controller alive for the whole test.
    container.listen(reviewControllerProvider, (_, _) {});
  });

  tearDown(() async {
    if (await root.exists()) await root.delete(recursive: true);
  });

  Future<File> kept(String name) async =>
      File('${root.path}/$name')..writeAsBytesSync(tinyPng);

  CaptureResult captured({File? image}) => CaptureResult(
    payload: CapturePayload(
      kind: CaptureKind.receipt,
      maskedText: 'MIGROS TOPLAM 270,30',
      captureDate: DateTime(2026, 11, 14),
      source: CaptureSource.gallery,
    ),
    maskedCounts: const {PiiType.phone: 0},
    pageCount: 1,
    retainedImage: image,
  );

  ReviewController controller() =>
      container.read(reviewControllerProvider.notifier);

  test('saving uploads the kept photo, then deletes the temporary copy', () async {
    final image = await kept('keep_1.jpg');
    await controller().start(captured(image: image));

    final outcome = await controller().save(rememberCategory: false);

    expect(outcome.imageUploaded, isTrue);
    final upload = documents.uploads.single;
    expect(upload.transactionId, outcome.detail!.purchase.id);
    expect(upload.mimeType, 'image/jpeg');
    expect(upload.type, 'RECEIPT_IMAGE');
    expect(image.existsSync(), isFalse);
  });

  test('a PDF is uploaded as an invoice', () async {
    final pdf = await kept('keep_2.pdf');
    await controller().start(captured(image: pdf));

    await controller().save(rememberCategory: false);

    expect(documents.uploads.single.mimeType, 'application/pdf');
    expect(documents.uploads.single.type, 'INVOICE');
  });

  test('one failed upload is retried once', () async {
    final image = await kept('keep_3.jpg');
    documents.failUploads = 1;
    await controller().start(captured(image: image));

    final outcome = await controller().save(rememberCategory: false);

    expect(outcome.imageUploaded, isTrue);
    expect(documents.uploads, hasLength(1));
  });

  test('when the upload keeps failing the purchase is still saved', () async {
    final image = await kept('keep_4.jpg');
    documents.failUploads = 5;
    await controller().start(captured(image: image));

    final outcome = await controller().save(rememberCategory: false);

    expect(outcome.imageUploaded, isFalse);
    expect(transactions.confirmed, hasLength(1));
    expect(documents.uploads, isEmpty);
    expect(image.existsSync(), isFalse); // the temporary copy never stays behind
  });

  test('a question keeps the image: nothing is created or uploaded yet', () async {
    final image = await kept('keep_6.jpg');
    transactions.nextSave = NeedsAnswer([_suggestion()]);
    await controller().start(captured(image: image));

    final outcome = await controller().save(rememberCategory: false);

    expect(outcome.needsAnswer, isTrue);
    expect(outcome.detail, isNull);
    expect(outcome.suggestions.single.id, 'd-1');
    expect(outcome.imageUploaded, isNull);
    expect(documents.uploads, isEmpty);
    expect(image.existsSync(), isTrue); // it waits for the answer
  });

  test('after the answer the image goes to the purchase that exists now', () async {
    final image = await kept('keep_7.jpg');
    transactions.nextSave = NeedsAnswer([_suggestion()]);
    await controller().start(captured(image: image));
    await controller().save(rememberCategory: false);
    final answered = transactions.add(id: 'tx-77');

    final uploaded = await controller().attachImageAfterAnswer(answered);

    expect(uploaded, isTrue);
    expect(documents.uploads.single.transactionId, 'tx-77');
    expect(image.existsSync(), isFalse);
  });

  test('a question left unanswered deletes the kept image', () async {
    final image = await kept('keep_8.jpg');
    transactions.nextSave = NeedsAnswer([_suggestion()]);
    await controller().start(captured(image: image));
    await controller().save(rememberCategory: false);

    await controller().dropImage();

    expect(image.existsSync(), isFalse);
    expect(documents.uploads, isEmpty);
  });

  test('a receipt merged into a purchase uploads its image there', () async {
    final image = await kept('keep_9.jpg');
    final target = transactions.add(id: 'tx-9');
    transactions.nextSave = Saved(
      PurchaseDetail(
        purchase: target.purchase,
        evidence: const [EvidenceKind.bank, EvidenceKind.receipt],
        lines: const [],
        documents: const [],
        merge: const MergeInfo(
          decisionId: 'd-1',
          observationId: 'obs-1',
          isAuto: true,
        ),
      ),
    );
    await controller().start(captured(image: image));

    final outcome = await controller().save(rememberCategory: false);

    expect(outcome.detail!.merge!.isAuto, isTrue);
    expect(documents.uploads.single.transactionId, 'tx-9');
    expect(image.existsSync(), isFalse);
  });

  test('no kept image: nothing to upload', () async {
    await controller().start(captured());
    final outcome = await controller().save(rememberCategory: false);
    expect(outcome.imageUploaded, isNull);
    expect(documents.uploads, isEmpty);
  });

  test('a failing save keeps the image for another try', () async {
    final image = await kept('keep_5.jpg');
    await controller().start(captured(image: image));
    transactions.writeError = fakeApiError('NETWORK_UNREACHABLE');

    await expectLater(
      controller().save(rememberCategory: false),
      throwsA(isA<Object>()),
    );

    expect(image.existsSync(), isTrue);
    expect(container.read(reviewControllerProvider).phase, ReviewPhase.editing);
    await controller().save(rememberCategory: false);
    expect(transactions.confirmed, hasLength(1));
  });

  test('discard rejects the observation and deletes the image', () async {
    final image = await kept('keep_6.jpg');
    await controller().start(captured(image: image));

    await controller().discard();

    expect(transactions.rejected, ['obs-1']);
    expect(image.existsSync(), isFalse);
  });

  test('discard still deletes the image when the server cannot be reached', () async {
    final image = await kept('keep_7.jpg');
    await controller().start(captured(image: image));
    transactions.rejectError = fakeApiError('NETWORK_UNREACHABLE');

    await controller().discard();

    expect(image.existsSync(), isFalse);
  });

  test('a changed category is noticed, an unchanged one is not', () async {
    await controller().start(captured());
    expect(controller().categoryWasChanged, isFalse);
    controller().setCategory(
      container.read(reviewControllerProvider).form!.category,
    );
    expect(controller().categoryWasChanged, isFalse);
  });

  test('the form of a failed reading is manual and saved without an observation', () async {
    extraction.error = fakeApiError('EXTRACTION_FAILED');
    await controller().start(captured());

    final state = container.read(reviewControllerProvider);
    expect(state.isManual, isTrue);
    expect(state.notice, isNotNull);
    controller().setMerchant('Bakkal');
    controller().setTotal(1250);
    await controller().save(rememberCategory: false);

    expect(transactions.confirmed, isEmpty);
    expect(transactions.created.single.totalMinor, 1250);
    expect(controller().categoryWasChanged, isFalse); // no rule for a manual entry
  });
}
