import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import 'core/storage/settings_store.dart';
import 'core/theme/app_theme.dart';
import 'features/assistant/presentation/assistant_screen.dart';
import 'features/auth/domain/auth_state.dart';
import 'features/auth/presentation/auth_controller.dart';
import 'features/auth/presentation/consent_screen.dart';
import 'features/auth/presentation/login_screen.dart';
import 'features/auth/presentation/register_screen.dart';
import 'features/auth/presentation/splash_screen.dart';
import 'features/capture/data/capture_providers.dart';
import 'features/capture/presentation/bank/bank_import_screen.dart';
import 'features/capture/presentation/camera_screen.dart';
import 'features/capture/presentation/capture_result_screen.dart';
import 'features/capture/presentation/pick_image_screen.dart';
import 'features/capture/presentation/review/review_screen.dart';
import 'features/home/presentation/home_screen.dart';
import 'features/products/presentation/add_product_screen.dart';
import 'features/products/presentation/products_screen.dart';
import 'features/settings/presentation/settings_screen.dart';
import 'features/shell/presentation/main_shell.dart';
import 'features/transactions/presentation/manual_transaction_screen.dart';
import 'features/transactions/presentation/transaction_detail_screen.dart';
import 'features/transactions/presentation/transactions_screen.dart';

part 'app.g.dart';

const _authPages = {'/login', '/register'};
const _preSessionPages = {'/splash', '/consent', '/login', '/register'};

/// Decides where the user must be, from the auth state alone. Returns null when [location]
/// is fine, otherwise the route to go to. (Kept pure so it can be tested without a router.)
///
/// Order: wait for the token check → first-run consent → sign in → the app.
String? appRedirect({
  required AuthState auth,
  required bool consentSeen,
  required bool hasAccount,
  required String location,
}) {
  if (auth.status == AuthStatus.checking ||
      auth.status == AuthStatus.unreachable) {
    return location == '/splash' ? null : '/splash';
  }
  if (!consentSeen) {
    return location == '/consent' ? null : '/consent';
  }
  if (auth.status == AuthStatus.unauthenticated) {
    if (_authPages.contains(location)) return null;
    // A device that has never had an account (or whose account was deleted) starts at
    // Register; everyone else at Login.
    return hasAccount ? '/login' : '/register';
  }
  // Signed in: the pre-session pages make no sense any more.
  return _preSessionPages.contains(location) ? '/home' : null;
}

final rootNavigatorKey = GlobalKey<NavigatorState>(debugLabel: 'root');

/// All routes are declared here (see CLAUDE.md conventions).
@Riverpod(keepAlive: true)
GoRouter router(Ref ref) {
  // Re-run the redirect whenever the auth state, consent or "has account" change.
  final refresh = ValueNotifier<int>(0);
  ref.onDispose(refresh.dispose);
  void bump(Object? previous, Object? next) => refresh.value++;
  ref.listen(authProvider, bump);
  ref.listen(consentSeenProvider, bump);
  ref.listen(hasAccountProvider, bump);

  return GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: '/splash',
    refreshListenable: refresh,
    redirect: (context, state) => appRedirect(
      auth: ref.read(authProvider),
      consentSeen: ref.read(consentSeenProvider),
      hasAccount: ref.read(hasAccountProvider),
      location: state.matchedLocation,
    ),
    routes: [
      GoRoute(
        path: '/splash',
        builder: (context, state) => const SplashScreen(),
      ),
      GoRoute(
        path: '/consent',
        builder: (context, state) => const ConsentScreen(),
      ),
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      GoRoute(
        path: '/register',
        builder: (context, state) => const RegisterScreen(),
      ),

      // The four tabs. The (+) in the bottom bar is not a tab: it opens a sheet.
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) =>
            MainShell(navigationShell: navigationShell),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/home',
                builder: (context, state) => const HomeScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/transactions',
                builder: (context, state) => const TransactionsScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/products',
                builder: (context, state) => const ProductsScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/assistant',
                builder: (context, state) => const AssistantScreen(),
              ),
            ],
          ),
        ],
      ),

      // Full-screen pages on top of the tabs (no bottom bar).
      GoRoute(
        path: '/settings',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const SettingsScreen(),
      ),
      GoRoute(
        path: '/capture/scan',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const CameraScreen(),
      ),
      GoRoute(
        path: '/capture/gallery',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const PickImageScreen.gallery(),
      ),
      GoRoute(
        path: '/capture/bank',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const PickImageScreen.bank(),
      ),
      GoRoute(
        path: '/capture/review',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const ReviewScreen(),
      ),
      GoRoute(
        path: '/capture/bank-import',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const BankImportScreen(),
      ),
      GoRoute(
        path: '/capture/result',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const CaptureResultScreen(),
      ),
      GoRoute(
        path: '/transactions/new',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const ManualTransactionScreen(),
      ),
      GoRoute(
        path: '/transactions/:id',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) =>
            TransactionDetailScreen(purchaseId: state.pathParameters['id']!),
      ),
      GoRoute(
        path: '/transactions/:id/edit',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) =>
            ManualTransactionScreen(purchaseId: state.pathParameters['id']),
      ),
      GoRoute(
        path: '/documents/:id/view',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => DocumentViewerScreen(
          documentId: state.pathParameters['id']!,
          isPdf: state.uri.queryParameters['pdf'] == 'true',
        ),
      ),
      GoRoute(
        path: '/products/new',
        parentNavigatorKey: rootNavigatorKey,
        builder: (context, state) => const AddProductScreen(),
      ),
    ],
  );
}

class ReceiptBoxApp extends ConsumerWidget {
  const ReceiptBoxApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Start listening for shared files right away (see SharedInbox).
    ref.read(sharedInboxProvider);
    return MaterialApp.router(
      title: 'ReceiptBox AI',
      routerConfig: ref.watch(routerProvider),
      theme: AppTheme.light(),
      // Turkish is the only UI language.
      locale: const Locale('tr', 'TR'),
      supportedLocales: const [Locale('tr', 'TR')],
      // Material + Widgets + Cupertino strings (Turkish) for built-in widgets.
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
    );
  }
}
