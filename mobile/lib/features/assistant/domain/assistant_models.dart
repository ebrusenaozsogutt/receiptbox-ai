/// The AI assistant's answers (backend P14, `POST /assistant/chat`).
library;

/// A deep link under an answer. Built by the backend from the tool results, never by the model.
enum AssistantActionType {
  openTransactions('OPEN_TRANSACTIONS'),
  openProduct('OPEN_PRODUCT'),
  openDocument('OPEN_DOCUMENT'),
  openInstallments('OPEN_INSTALLMENTS');

  const AssistantActionType(this.key);

  final String key;

  static AssistantActionType? fromKey(String? key) {
    for (final type in values) {
      if (type.key == key) return type;
    }
    return null;
  }
}

class AssistantAction {
  const AssistantAction({
    required this.type,
    required this.label,
    this.params = const {},
  });

  final AssistantActionType type;

  /// Turkish button text from the backend ("Harcamaları gör", "AirPods Pro kartı").
  final String label;

  /// OPEN_TRANSACTIONS: from, to (YYYY-MM-DD), category, q. OPEN_PRODUCT: id.
  /// OPEN_DOCUMENT: id, pdf ("true"/"false"). OPEN_INSTALLMENTS: month (YYYY-MM).
  final Map<String, String> params;

  /// Null for an action type this version of the app does not know (it is not shown).
  static AssistantAction? fromJson(Map<String, dynamic> json) {
    final type = AssistantActionType.fromKey(json['type'] as String?);
    if (type == null) return null;
    final params = json['params'] as Map<String, dynamic>? ?? const {};
    return AssistantAction(
      type: type,
      label: json['label'] as String? ?? '',
      params: {for (final entry in params.entries) entry.key: '${entry.value}'},
    );
  }
}

class AssistantReply {
  const AssistantReply({
    required this.answer,
    this.actions = const [],
    this.tools = const [],
  });

  final String answer;
  final List<AssistantAction> actions;

  /// The names of the tools the assistant used (shown nowhere; kept for debugging).
  final List<String> tools;

  factory AssistantReply.fromJson(Map<String, dynamic> json) => AssistantReply(
    answer: json['answer'] as String? ?? '',
    actions: [
      for (final item in json['actions'] as List<dynamic>? ?? const [])
        ?AssistantAction.fromJson(item as Map<String, dynamic>),
    ],
    tools: [
      for (final item in json['tool_calls'] as List<dynamic>? ?? const [])
        (item as Map<String, dynamic>)['name'] as String,
    ],
  );
}

/// One question on the screen and what came back: an answer, an error or nothing yet.
class ChatExchange {
  const ChatExchange({required this.question, this.reply, this.error});

  final String question;
  final AssistantReply? reply;

  /// Turkish error text (the question can be asked again with "Tekrar dene").
  final String? error;

  bool get pending => reply == null && error == null;
}

/// The questions that fill the empty chat (phase P14).
const suggestedQuestions = [
  'Bu ay markete ne kadar harcadım?',
  'Garantisi bitecek ürünler?',
  'Kalan taksitlerim ne kadar?',
  'En pahalı 5 alışverişim?',
  'Kulaklığın faturası nerede?',
];
