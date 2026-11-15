import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import 'features/health/presentation/health_screen.dart';

part 'app.g.dart';

/// All routes are declared here (see CLAUDE.md conventions).
@Riverpod(keepAlive: true)
GoRouter router(Ref ref) {
  return GoRouter(
    routes: [
      GoRoute(path: '/', builder: (context, state) => const HealthScreen()),
    ],
  );
}

class ReceiptBoxApp extends ConsumerWidget {
  const ReceiptBoxApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      title: 'ReceiptBox AI',
      routerConfig: ref.watch(routerProvider),
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal),
        useMaterial3: true,
      ),
      // Turkish is the only UI language.
      locale: const Locale('tr', 'TR'),
      supportedLocales: const [Locale('tr', 'TR')],
      // Material + Widgets + Cupertino strings (Turkish) for built-in widgets.
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
    );
  }
}
