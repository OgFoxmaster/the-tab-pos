import 'package:flutter_test/flutter_test.dart';
import 'package:the_tab_pos/pos_app.dart';

void main() {
  testWidgets('shows an online sign-in form without demo credentials',
      (tester) async {
    await tester.pumpWidget(const TheTabApp());

    expect(find.text('The Tab POS'), findsOneWidget);
    expect(find.text('Sign in with your staff account'), findsOneWidget);
    expect(find.text('An internet connection to the POS server is required.'),
        findsOneWidget);
    expect(find.text('Owner@123'), findsNothing);
  });
}
