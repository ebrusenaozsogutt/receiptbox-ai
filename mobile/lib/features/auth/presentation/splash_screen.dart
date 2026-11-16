import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:material_ui/material_ui.dart';

import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../domain/auth_state.dart';
import 'auth_controller.dart';
import 'auth_scaffold.dart';

/// Shown while the stored tokens are checked. The router leaves it as soon as the answer is
/// known; it stays only when the server cannot be reached (with a retry button).
class SplashScreen extends ConsumerWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    return Scaffold(
      body: SafeArea(
        child: auth.status == AuthStatus.unreachable
            ? ErrorView(
                message: auth.message ?? '',
                onRetry: () => ref.read(authProvider.notifier).restore(),
              )
            : const Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [BrandHeader(), LoadingView()],
              ),
      ),
    );
  }
}
