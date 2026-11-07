import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

void main() {
  runApp(const TheTabApp());
}

class AppUser {
  const AppUser({
    required this.username,
    required this.fullName,
    required this.role,
    required this.token,
  });

  final String username;
  final String fullName;
  final String role;
  final String token;

  factory AppUser.fromJson(Map<String, dynamic> json, String token) {
    return AppUser(
      username: json['username']?.toString() ?? '',
      fullName:
          json['full_name']?.toString() ?? json['username']?.toString() ?? '',
      role: json['role']?.toString().toLowerCase() ?? 'cashier',
      token: token,
    );
  }
}

class Product {
  const Product({
    required this.id,
    required this.name,
    required this.category,
    required this.price,
    required this.stock,
    required this.reorderLevel,
    required this.sku,
  });

  final int id;
  final String name;
  final String category;
  final double price;
  final int stock;
  final int reorderLevel;
  final String sku;

  factory Product.fromJson(Map<String, dynamic> json) {
    return Product(
      id: int.parse(json['id'].toString()),
      name: json['name']?.toString() ?? 'Unknown product',
      category: json['category']?.toString() ?? 'General',
      price: double.parse((json['selling_price'] ?? 0).toString()),
      stock: int.parse((json['stock_quantity'] ?? 0).toString()),
      reorderLevel: int.parse((json['reorder_level'] ?? 0).toString()),
      sku: json['sku']?.toString() ?? '',
    );
  }
}

class CartItem {
  const CartItem({required this.product, required this.quantity});

  final Product product;
  final int quantity;

  double get total => product.price * quantity;
}

class ApiService {
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static Future<dynamic> _request(
    String path, {
    String? token,
    String method = 'GET',
    Map<String, dynamic>? body,
  }) async {
    final uri = Uri.parse('$baseUrl$path');
    final headers = <String, String>{
      if (body != null) 'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };

    late final http.Response response;
    try {
      if (method == 'POST') {
        response = await http
            .post(uri, headers: headers, body: jsonEncode(body))
            .timeout(const Duration(seconds: 90));
      } else {
        response = await http
            .get(uri, headers: headers)
            .timeout(const Duration(seconds: 90));
      }
    } on Exception catch (error) {
      throw Exception(
          'Could not connect to the POS server at $baseUrl: $error');
    }

    dynamic data;
    if (response.body.isNotEmpty) {
      try {
        data = jsonDecode(response.body);
      } on FormatException {
        throw Exception('The POS server returned an invalid response.');
      }
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = data is Map<String, dynamic>
          ? (data['detail'] ?? data['message'] ?? 'Request failed').toString()
          : 'Request failed (${response.statusCode})';
      throw Exception(detail);
    }
    return data;
  }

  static Future<Map<String, dynamic>> loginChallenge(
    String username,
    String password, {
    String? code,
    String? challenge,
  }) async {
    return await _request(
      '/login',
      method: 'POST',
      body: {
        'username': username,
        'password': password,
        if (code != null) 'login_code': code,
        if (challenge != null) 'login_challenge': challenge,
      },
    ) as Map<String, dynamic>;
  }

  static Future<AppUser> login(String username, String password, String code, String challenge) async {
    final result = await loginChallenge(username, password, code: code, challenge: challenge);
    final token = result['access_token']?.toString() ?? '';
    if (token.isEmpty) throw Exception('The server did not return a sign-in token.');
    final profile = await _request('/me', token: token) as Map<String, dynamic>;
    return AppUser.fromJson(profile, token);
  }

  static Future<List<Product>> fetchProducts(String token) async {
    final result = await _request('/products', token: token) as List<dynamic>;
    return result
        .map((item) => Product.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  static Future<Map<String, dynamic>> fetchSummary(String token) async {
    return await _request('/dashboard/summary', token: token)
        as Map<String, dynamic>;
  }

  static Future<List<Map<String, dynamic>>> fetchSales(String token) async {
    final result = await _request('/sales', token: token) as List<dynamic>;
    return result.cast<Map<String, dynamic>>();
  }

  static Future<List<Map<String, dynamic>>> fetchExpenses(String token) async {
    final result = await _request('/expenses', token: token) as List<dynamic>;
    return result.cast<Map<String, dynamic>>();
  }

  static Future<void> checkout(String token, List<CartItem> cart) async {
    await _request(
      '/sales',
      token: token,
      method: 'POST',
      body: {
        'payment_method': 'cash',
        'items': cart
            .map((item) => {
                  'product_id': item.product.id,
                  'quantity': item.quantity,
                })
            .toList(),
      },
    );
  }

  static Future<void> receiveStock(
    String token,
    int productId,
    int quantity,
  ) async {
    await _request(
      '/inventory/movement',
      token: token,
      method: 'POST',
      body: {
        'product_id': productId,
        'quantity': quantity,
        'type': 'receive',
        'note': 'Stock received',
      },
    );
  }

  static Future<void> createExpense(
    String token, {
    required String description,
    required String category,
    required double amount,
    required String paymentMethod,
  }) async {
    await _request(
      '/expenses',
      token: token,
      method: 'POST',
      body: {
        'description': description,
        'category': category,
        'amount': amount,
        'payment_method': paymentMethod,
      },
    );
  }
}

String formatKSh(num value) {
  final rounded = value.toStringAsFixed(2);
  final parts = rounded.split('.');
  final whole = parts[0].replaceAllMapped(
    RegExp(r'\B(?=(\d{3})+(?!\d))'),
    (match) => ',',
  );
  return 'KSh $whole.${parts[1]}';
}

String errorMessage(Object error) =>
    error.toString().replaceFirst('Exception: ', '');

class TheTabApp extends StatelessWidget {
  const TheTabApp({super.key});

  @override
  Widget build(BuildContext context) {
    const green = Color(0xFF245C46);
    return MaterialApp(
      title: 'The Tab POS',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: green, primary: green),
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFFF5F6F3),
        inputDecorationTheme: const InputDecorationTheme(
          border: OutlineInputBorder(),
          filled: true,
          fillColor: Colors.white,
        ),
        cardTheme: CardTheme(
          color: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(
            side: const BorderSide(color: Color(0xFFE8EBE7)),
            borderRadius: BorderRadius.circular(14),
          ),
        ),
      ),
      home: const LoginPage(),
    );
  }
}

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  final _codeController = TextEditingController();
  String? _challenge;
  String? _developmentCode;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _signIn() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final challenge = await ApiService.loginChallenge(
        _usernameController.text.trim(),
        _passwordController.text,
        code: _challenge == null ? null : _codeController.text.trim(),
        challenge: _challenge,
      );
      if (challenge['requires_login_code'] == true) {
        if (!mounted) return;
        setState(() {
          _challenge = challenge['login_challenge']?.toString();
          _developmentCode = challenge['dev_login_code']?.toString();
        });
        return;
      }
      final token = challenge['access_token']?.toString() ?? '';
      if (token.isEmpty) throw Exception('The server did not return a sign-in token.');
      final profile = await ApiService._request('/me', token: token) as Map<String, dynamic>;
      final user = AppUser.fromJson(profile, token);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => HomePage(user: user)),
      );
    } catch (error) {
      if (mounted) setState(() => _error = errorMessage(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(26),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Icon(Icons.local_bar,
                        size: 44, color: Color(0xFF245C46)),
                    const SizedBox(height: 12),
                    const Text(
                      'The Tab POS',
                      textAlign: TextAlign.center,
                      style:
                          TextStyle(fontSize: 28, fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 5),
                    const Text(
                      'Sign in with your staff account',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.black54),
                    ),
                    const SizedBox(height: 24),
                    TextField(
                      controller: _usernameController,
                      textInputAction: TextInputAction.next,
                      autofillHints: const [AutofillHints.username],
                      decoration: const InputDecoration(labelText: 'Username'),
                    ),
                    const SizedBox(height: 14),
                    if (_challenge != null) ...[
                      TextField(
                        controller: _codeController,
                        keyboardType: TextInputType.number,
                        decoration: InputDecoration(labelText: _developmentCode == null ? 'Login code' : 'Login code (development: $_developmentCode)'),
                      ),
                      const SizedBox(height: 14),
                    ],
                    TextField(
                      controller: _passwordController,
                      obscureText: true,
                      onSubmitted: (_) => _busy ? null : _signIn(),
                      autofillHints: const [AutofillHints.password],
                      decoration: const InputDecoration(labelText: 'Password'),
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: 12),
                      Text(_error!, style: const TextStyle(color: Colors.red)),
                    ],
                    const SizedBox(height: 18),
                    FilledButton(
                      onPressed: _busy ? null : _signIn,
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 11),
                        child: Text(_busy ? 'Signing in…' : 'Sign in'),
                      ),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'An internet connection is required. The first sign-in can take up to a minute while the server wakes up.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.black45, fontSize: 12),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key, required this.user});

  final AppUser user;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  late final List<String> _pages;
  int _selectedPage = 0;
  bool _loading = true;
  bool _saving = false;
  String? _error;
  String? _notice;
  List<Product> _products = [];
  List<CartItem> _cart = [];
  List<Map<String, dynamic>> _sales = [];
  List<Map<String, dynamic>> _expenses = [];
  Map<String, dynamic> _summary = {};
  String _search = '';

  @override
  void initState() {
    super.initState();
    _pages = switch (widget.user.role) {
      'stock' => ['Inventory'],
      'cashier' => ['Dashboard', 'POS', 'Sales'],
      _ => ['Dashboard', 'POS', 'Inventory', 'Sales', 'Expenses'],
    };
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final products = await ApiService.fetchProducts(widget.user.token);
      final summary = await ApiService.fetchSummary(widget.user.token);
      final sales = widget.user.role == 'stock'
          ? <Map<String, dynamic>>[]
          : await ApiService.fetchSales(widget.user.token);
      final expenses =
          widget.user.role == 'owner' || widget.user.role == 'manager'
              ? await ApiService.fetchExpenses(widget.user.token)
              : <Map<String, dynamic>>[];
      if (!mounted) return;
      setState(() {
        _products = products;
        _summary = summary;
        _sales = sales;
        _expenses = expenses;
      });
    } catch (error) {
      if (mounted) setState(() => _error = errorMessage(error));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<CartItem> get _currentCart => _cart;
  double get _cartTotal => _cart.fold(0, (total, item) => total + item.total);

  void _addProduct(Product product) {
    if (product.stock <= 0) {
      setState(() => _notice = '${product.name} is out of stock.');
      return;
    }
    final currentIndex =
        _cart.indexWhere((item) => item.product.id == product.id);
    if (currentIndex >= 0 && _cart[currentIndex].quantity >= product.stock) {
      setState(() => _notice =
          'Only ${product.stock} units of ${product.name} are available.');
      return;
    }
    setState(() {
      _notice = null;
      if (currentIndex < 0) {
        _cart = [..._cart, CartItem(product: product, quantity: 1)];
      } else {
        _cart = _cart
            .map((item) => item.product.id == product.id
                ? CartItem(product: product, quantity: item.quantity + 1)
                : item)
            .toList();
      }
    });
  }

  void _changeQuantity(Product product, int amount) {
    setState(() {
      _cart = _cart
          .map((item) => item.product.id == product.id
              ? CartItem(
                  product: product,
                  quantity:
                      (item.quantity + amount).clamp(0, product.stock).toInt(),
                )
              : item)
          .where((item) => item.quantity > 0)
          .toList();
    });
  }

  Future<void> _checkout() async {
    if (_cart.isEmpty || _saving) return;
    setState(() {
      _saving = true;
      _notice = null;
    });
    final amount = _cartTotal;
    try {
      await ApiService.checkout(widget.user.token, _cart);
      if (!mounted) return;
      setState(() {
        _cart = [];
        _notice = 'Cash sale completed for ${formatKSh(amount)}.';
      });
      await _loadData();
    } catch (error) {
      if (mounted) {
        setState(
            () => _notice = 'Sale was not completed: ${errorMessage(error)}');
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _receiveStock(Product product, int quantity) async {
    await ApiService.receiveStock(widget.user.token, product.id, quantity);
    await _loadData();
    if (mounted) setState(() => _notice = 'Stock updated for ${product.name}.');
  }

  Future<void> _addExpense({
    required String description,
    required String category,
    required double amount,
    required String paymentMethod,
  }) async {
    await ApiService.createExpense(
      widget.user.token,
      description: description,
      category: category,
      amount: amount,
      paymentMethod: paymentMethod,
    );
    await _loadData();
    if (mounted) setState(() => _notice = 'Expense recorded.');
  }

  Future<void> _signOut() async {
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const LoginPage()),
      (_) => false,
    );
  }

  Widget _buildPage(String page) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return _ErrorPanel(message: _error!, onRetry: _loadData);
    }
    return switch (page) {
      'Dashboard' => _DashboardView(
          summary: _summary,
          products: _products,
          sales: _sales,
          role: widget.user.role,
        ),
      'POS' => _PosView(
          products: _products,
          cart: _currentCart,
          search: _search,
          onSearch: (value) => setState(() => _search = value),
          onAdd: _addProduct,
          onQuantity: _changeQuantity,
          total: _cartTotal,
          notice: _notice,
          saving: _saving,
          onCheckout: _checkout,
        ),
      'Inventory' => _InventoryView(
          products: _products,
          canReceive: true,
          onReceive: _receiveStock,
        ),
      'Sales' => _SalesView(sales: _sales),
      'Expenses' => _ExpensesView(
          expenses: _expenses,
          saving: _saving,
          onAdd: _addExpense,
        ),
      _ => const SizedBox.shrink(),
    };
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('The Tab · ${_pages[_selectedPage]}',
                style: const TextStyle(fontWeight: FontWeight.w700)),
            Text(
              '${widget.user.fullName} · ${widget.user.role}',
              style: Theme.of(context).textTheme.labelSmall,
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Refresh shared data',
            onPressed: _loading ? null : _loadData,
            icon: const Icon(Icons.refresh),
          ),
          IconButton(
            tooltip: 'Sign out',
            onPressed: _signOut,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            if (_notice != null)
              MaterialBanner(
                content: Text(_notice!),
                actions: [
                  TextButton(
                    onPressed: () => setState(() => _notice = null),
                    child: const Text('Dismiss'),
                  ),
                ],
              ),
            Expanded(child: _buildPage(_pages[_selectedPage])),
          ],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedPage,
        onDestinationSelected: (index) {
          setState(() {
            _selectedPage = index;
            _notice = null;
          });
        },
        destinations: [
          for (final page in _pages)
            NavigationDestination(
              icon: Icon(_iconForPage(page)),
              label: page,
            ),
        ],
      ),
    );
  }
}

IconData _iconForPage(String page) => switch (page) {
      'Dashboard' => Icons.dashboard_outlined,
      'POS' => Icons.point_of_sale,
      'Inventory' => Icons.inventory_2_outlined,
      'Sales' => Icons.receipt_long_outlined,
      'Expenses' => Icons.payments_outlined,
      _ => Icons.circle_outlined,
    };

class _DashboardView extends StatelessWidget {
  const _DashboardView({
    required this.summary,
    required this.products,
    required this.sales,
    required this.role,
  });

  final Map<String, dynamic> summary;
  final List<Product> products;
  final List<Map<String, dynamic>> sales;
  final String role;

  @override
  Widget build(BuildContext context) {
    final lowStock = products
        .where((product) => product.stock <= product.reorderLevel)
        .toList();
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Operations overview',
            style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            _StatCard(
                label: 'Sales recorded',
                value: '${summary['total_sales'] ?? 0}'),
            _StatCard(
                label: 'Sales revenue',
                value: formatKSh((summary['total_revenue'] as num?) ?? 0)),
            _StatCard(
                label: 'Products', value: '${summary['total_products'] ?? 0}'),
            _StatCard(
                label: 'Low stock', value: '${summary['low_stock'] ?? 0}'),
          ],
        ),
        const SizedBox(height: 18),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                    role == 'cashier'
                        ? 'Your recent sales'
                        : 'Low-stock products',
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                if (role == 'cashier')
                  if (sales.isEmpty)
                    const Text('No sales recorded yet.')
                  else
                    ...sales.take(5).map((sale) => ListTile(
                          contentPadding: EdgeInsets.zero,
                          title:
                              Text(sale['sale_number']?.toString() ?? 'Sale'),
                          subtitle:
                              Text(sale['payment_status']?.toString() ?? ''),
                          trailing:
                              Text(formatKSh((sale['total'] as num?) ?? 0)),
                        ))
                else if (lowStock.isEmpty)
                  const Text('No products need restocking.')
                else
                  ...lowStock.take(8).map((product) => ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(product.name),
                        subtitle: Text('Reorder at ${product.reorderLevel}'),
                        trailing: Text('${product.stock} left'),
                      )),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: (MediaQuery.sizeOf(context).width - 44) / 2,
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(15),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label,
                  style: const TextStyle(color: Colors.black54, fontSize: 12)),
              const SizedBox(height: 8),
              Text(value,
                  style: const TextStyle(
                      fontSize: 18, fontWeight: FontWeight.w800)),
            ],
          ),
        ),
      ),
    );
  }
}

class _PosView extends StatelessWidget {
  const _PosView({
    required this.products,
    required this.cart,
    required this.search,
    required this.onSearch,
    required this.onAdd,
    required this.onQuantity,
    required this.total,
    required this.notice,
    required this.saving,
    required this.onCheckout,
  });

  final List<Product> products;
  final List<CartItem> cart;
  final String search;
  final ValueChanged<String> onSearch;
  final ValueChanged<Product> onAdd;
  final void Function(Product, int) onQuantity;
  final double total;
  final String? notice;
  final bool saving;
  final VoidCallback onCheckout;

  @override
  Widget build(BuildContext context) {
    final query = search.toLowerCase();
    final filtered = products
        .where((product) => '${product.name} ${product.sku} ${product.category}'
            .toLowerCase()
            .contains(query))
        .toList();

    return LayoutBuilder(
      builder: (context, constraints) {
        final catalog = Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
              child: TextField(
                onChanged: onSearch,
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search),
                  hintText: 'Search name, SKU or category',
                ),
              ),
            ),
            Expanded(
              child: GridView.builder(
                padding: const EdgeInsets.all(10),
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: constraints.maxWidth > 650 ? 3 : 2,
                  crossAxisSpacing: 8,
                  mainAxisSpacing: 8,
                  childAspectRatio: 1.08,
                ),
                itemCount: filtered.length,
                itemBuilder: (context, index) {
                  final product = filtered[index];
                  return Card(
                    child: InkWell(
                      borderRadius: BorderRadius.circular(14),
                      onTap: product.stock > 0 ? () => onAdd(product) : null,
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(product.category,
                                style: const TextStyle(
                                    color: Colors.black54, fontSize: 11)),
                            const SizedBox(height: 5),
                            Text(product.name,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w700)),
                            const Spacer(),
                            Text(formatKSh(product.price),
                                style: const TextStyle(
                                    fontWeight: FontWeight.w800)),
                            const SizedBox(height: 3),
                            Text('${product.stock} available',
                                style: const TextStyle(fontSize: 11)),
                          ],
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        );

        final cartPanel = _CartPanel(
          cart: cart,
          total: total,
          notice: notice,
          saving: saving,
          onQuantity: onQuantity,
          onCheckout: onCheckout,
        );

        if (constraints.maxWidth > 780) {
          return Row(
            children: [
              Expanded(flex: 3, child: catalog),
              SizedBox(width: 350, child: cartPanel),
            ],
          );
        }
        return Column(
          children: [
            Expanded(flex: 3, child: catalog),
            SizedBox(height: 260, child: cartPanel),
          ],
        );
      },
    );
  }
}

class _CartPanel extends StatelessWidget {
  const _CartPanel({
    required this.cart,
    required this.total,
    required this.notice,
    required this.saving,
    required this.onQuantity,
    required this.onCheckout,
  });

  final List<CartItem> cart;
  final double total;
  final String? notice;
  final bool saving;
  final void Function(Product, int) onQuantity;
  final VoidCallback onCheckout;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.all(10),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Current sale',
                style: Theme.of(context).textTheme.titleMedium),
            const Divider(),
            Expanded(
              child: cart.isEmpty
                  ? const Center(
                      child: Text('Select products to add them to the cart.'))
                  : ListView(
                      children: cart
                          .map((item) => ListTile(
                                contentPadding: EdgeInsets.zero,
                                title: Text(item.product.name,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis),
                                subtitle: Text(
                                    '${formatKSh(item.product.price)} each'),
                                leading: IconButton(
                                  tooltip: 'Remove one',
                                  onPressed: () => onQuantity(item.product, -1),
                                  icon: const Icon(Icons.remove_circle_outline),
                                ),
                                trailing: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Text('${item.quantity}'),
                                    IconButton(
                                      tooltip: 'Add one',
                                      onPressed: item.quantity >=
                                              item.product.stock
                                          ? null
                                          : () => onQuantity(item.product, 1),
                                      icon:
                                          const Icon(Icons.add_circle_outline),
                                    ),
                                  ],
                                ),
                              ))
                          .toList(),
                    ),
            ),
            const Divider(),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Total due'),
                Text(formatKSh(total),
                    style: const TextStyle(fontWeight: FontWeight.w800)),
              ],
            ),
            const SizedBox(height: 7),
            const Text(
              'Cash checkout is enabled. M-Pesa and card require verified payment providers.',
              style: TextStyle(fontSize: 10, color: Colors.black54),
            ),
            if (notice != null) ...[
              const SizedBox(height: 5),
              Text(notice!,
                  style: const TextStyle(color: Colors.red, fontSize: 11)),
            ],
            const SizedBox(height: 8),
            FilledButton(
              onPressed: cart.isEmpty || saving ? null : onCheckout,
              child: Text(saving ? 'Processing…' : 'Complete cash sale'),
            ),
          ],
        ),
      ),
    );
  }
}

class _InventoryView extends StatelessWidget {
  const _InventoryView({
    required this.products,
    required this.canReceive,
    required this.onReceive,
  });

  final List<Product> products;
  final bool canReceive;
  final Future<void> Function(Product, int) onReceive;

  Future<void> _showReceiveDialog(BuildContext context, Product product) async {
    final controller = TextEditingController(text: '1');
    final quantity = await showDialog<int>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Receive ${product.name}'),
        content: TextField(
          controller: controller,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Quantity'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel')),
          FilledButton(
            onPressed: () {
              final amount = int.tryParse(controller.text);
              if (amount != null && amount > 0) Navigator.pop(context, amount);
            },
            child: const Text('Record'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (quantity == null) return;
    try {
      await onReceive(product, quantity);
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(errorMessage(error))),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        Text('Shared inventory', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        ...products.map((product) {
          final low = product.stock <= product.reorderLevel;
          return Card(
            child: ListTile(
              title: Text(product.name),
              subtitle: Text(
                  '${product.category} · ${product.sku} · Reorder at ${product.reorderLevel}'),
              leading: Icon(low ? Icons.warning_amber : Icons.inventory_2,
                  color: low ? Colors.deepOrange : Colors.green),
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('${product.stock}',
                      style: const TextStyle(fontWeight: FontWeight.w700)),
                  if (canReceive)
                    IconButton(
                      tooltip: 'Receive stock',
                      onPressed: () => _showReceiveDialog(context, product),
                      icon: const Icon(Icons.add_box_outlined),
                    ),
                ],
              ),
            ),
          );
        }),
        if (products.isEmpty)
          const Padding(
            padding: EdgeInsets.all(24),
            child: Center(child: Text('No active products in the catalog.')),
          ),
      ],
    );
  }
}

class _SalesView extends StatelessWidget {
  const _SalesView({required this.sales});

  final List<Map<String, dynamic>> sales;

  @override
  Widget build(BuildContext context) {
    if (sales.isEmpty) {
      return const Center(child: Text('No sales have been recorded.'));
    }
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        Text('Sales history', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        ...sales.map((sale) {
          final date = DateTime.tryParse(sale['sale_time']?.toString() ?? '');
          return Card(
            child: ListTile(
              title: Text(sale['sale_number']?.toString() ?? 'Sale'),
              subtitle: Text(
                '${date?.toLocal().toString().substring(0, 16) ?? 'Date unavailable'} · '
                '${sale['payment_method'] ?? 'cash'} · ${sale['payment_status'] ?? 'unknown'}',
              ),
              trailing: Text(
                formatKSh((sale['total'] as num?) ?? 0),
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
            ),
          );
        }),
      ],
    );
  }
}

class _ExpensesView extends StatelessWidget {
  const _ExpensesView({
    required this.expenses,
    required this.saving,
    required this.onAdd,
  });

  final List<Map<String, dynamic>> expenses;
  final bool saving;
  final Future<void> Function({
    required String description,
    required String category,
    required double amount,
    required String paymentMethod,
  }) onAdd;

  Future<void> _createExpense(BuildContext context) async {
    final description = TextEditingController();
    final category = TextEditingController(text: 'General');
    final amount = TextEditingController();
    String paymentMethod = 'cash';
    final formKey = GlobalKey<FormState>();
    final values = await showDialog<Map<String, String>>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Record expense'),
        content: Form(
          key: formKey,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextFormField(
                  controller: description,
                  decoration: const InputDecoration(labelText: 'Description'),
                  validator: (value) => value == null || value.trim().isEmpty
                      ? 'Enter a description'
                      : null,
                ),
                const SizedBox(height: 10),
                TextField(
                    controller: category,
                    decoration: const InputDecoration(labelText: 'Category')),
                const SizedBox(height: 10),
                TextFormField(
                  controller: amount,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(labelText: 'Amount (KSh)'),
                  validator: (value) {
                    final parsed = double.tryParse(value ?? '');
                    return parsed == null || parsed <= 0
                        ? 'Enter an amount above zero'
                        : null;
                  },
                ),
                const SizedBox(height: 10),
                StatefulBuilder(
                  builder: (context, setDialogState) =>
                      DropdownButtonFormField<String>(
                    value: paymentMethod,
                    decoration:
                        const InputDecoration(labelText: 'Payment method'),
                    items: const [
                      DropdownMenuItem(value: 'cash', child: Text('Cash')),
                      DropdownMenuItem(value: 'mpesa', child: Text('M-Pesa')),
                      DropdownMenuItem(value: 'card', child: Text('Card')),
                    ],
                    onChanged: (value) =>
                        setDialogState(() => paymentMethod = value ?? 'cash'),
                  ),
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              if (formKey.currentState?.validate() ?? false) {
                Navigator.pop(context, {
                  'description': description.text.trim(),
                  'category': category.text.trim(),
                  'amount': amount.text,
                  'payment_method': paymentMethod,
                });
              }
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
    description.dispose();
    category.dispose();
    amount.dispose();
    if (values == null) return;
    try {
      await onAdd(
        description: values['description']!,
        category: values['category']!,
        amount: double.parse(values['amount']!),
        paymentMethod: values['payment_method']!,
      );
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(errorMessage(error))),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Expenses', style: Theme.of(context).textTheme.titleLarge),
            FilledButton.icon(
              onPressed: saving ? null : () => _createExpense(context),
              icon: const Icon(Icons.add),
              label: const Text('Add'),
            ),
          ],
        ),
        const SizedBox(height: 8),
        ...expenses.map((expense) => Card(
              child: ListTile(
                title: Text(expense['description']?.toString() ?? ''),
                subtitle: Text(
                    '${expense['category'] ?? 'General'} · ${expense['payment_method'] ?? 'cash'}'),
                trailing: Text(formatKSh((expense['amount'] as num?) ?? 0)),
              ),
            )),
        if (expenses.isEmpty)
          const Padding(
            padding: EdgeInsets.all(24),
            child: Center(child: Text('No expenses recorded.')),
          ),
      ],
    );
  }
}

class _ErrorPanel extends StatelessWidget {
  const _ErrorPanel({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off_outlined,
                size: 42, color: Colors.deepOrange),
            const SizedBox(height: 12),
            const Text('Could not load live POS data',
                style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 14),
            OutlinedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Try again'),
            ),
          ],
        ),
      ),
    );
  }
}
