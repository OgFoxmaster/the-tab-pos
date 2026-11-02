import React, { useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom/client';
import './style.css';

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js').catch((error) => {
      console.error('Unable to register the POS app service worker.', error);
    });
  });
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const ROLE_PAGES = {
  owner: ['Dashboard', 'POS', 'Sales', 'Inventory', 'Expenses', 'Users'],
  manager: ['Dashboard', 'POS', 'Sales', 'Inventory', 'Expenses', 'Users'],
  stock: ['Inventory'],
  cashier: ['Dashboard', 'POS', 'Sales'],
};

async function request(path, token, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new Error(`Could not connect to the POS server at ${API_BASE_URL}.`);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(data?.detail || data?.message || 'The request could not be completed.');
    error.status = response.status;
    throw error;
  }
  return data;
}

function money(value) {
  return `KSh ${Number(value || 0).toLocaleString('en-KE', { maximumFractionDigits: 2 })}`;
}

function Login({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await request('/login', null, {
        method: 'POST',
        body: JSON.stringify({ username: username.trim(), password }),
      });
      const user = await request('/me', result.access_token);
      onLogin(result.access_token, user);
    } catch (reason) {
      setError(reason.message || 'Sign in failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="brand-mark">T</div>
        <p className="eyebrow">THE TAB · LIQUOR STORE</p>
        <h1>Welcome back</h1>
        <p className="muted">Sign in with your staff account to continue.</p>
        <label>Username
          <input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required />
        </label>
        <label>Password
          <input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        </label>
        {error && <p className="notice error" role="alert">{error}</p>}
        <button className="primary-btn full-width" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        <p className="login-footnote">An internet connection to the POS server is required.</p>
      </form>
    </main>
  );
}

function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem('tabpos.token') || '');
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem('tabpos.user') || 'null');
    } catch {
      return null;
    }
  });
  const [page, setPage] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    if (!token) return;
    request('/me', token).then((currentUser) => {
      setUser(currentUser);
      sessionStorage.setItem('tabpos.user', JSON.stringify(currentUser));
    }).catch((error) => {
      if (error.status === 401) signOut();
      else setNotice(error.message);
    });
  }, [token]);

  const pages = ROLE_PAGES[user?.role] || [];
  useEffect(() => {
    if (pages.length && !pages.includes(page)) setPage(pages[0]);
  }, [pages, page]);

  function signIn(accessToken, currentUser) {
    sessionStorage.setItem('tabpos.token', accessToken);
    sessionStorage.setItem('tabpos.user', JSON.stringify(currentUser));
    setToken(accessToken);
    setUser(currentUser);
    setNotice('');
  }

  function signOut() {
    sessionStorage.removeItem('tabpos.token');
    sessionStorage.removeItem('tabpos.user');
    setToken('');
    setUser(null);
    setPage('');
  }

  if (!token || !user) return <Login onLogin={signIn} />;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" onClick={(event) => { event.preventDefault(); setPage(pages[0]); }}>
          <span className="brand-mark small">T</span>
          <span><strong>The Tab</strong><small>POINT OF SALE</small></span>
        </a>
        <p className="nav-caption">WORKSPACE</p>
        <nav aria-label="Main navigation">
          {pages.map((item) => (
            <button key={item} className={`nav-item ${page === item ? 'active' : ''}`} onClick={() => { setPage(item); setNotice(''); }}>
              <span className="nav-icon">{({ Dashboard: '◫', POS: '＋', Sales: '▤', Inventory: '▦', Expenses: '↗', Users: '♙' })[item]}</span>
              {item}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="status-dot" /> Connected to shared POS
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div>
            <p className="eyebrow">THE TAB POS / {user.role.toUpperCase()}</p>
            <h1>{page}</h1>
          </div>
          <div className="profile">
            <div className="avatar">{(user.full_name || user.username || '?').slice(0, 1).toUpperCase()}</div>
            <div className="profile-name"><strong>{user.full_name || user.username}</strong><small>{user.role}</small></div>
            <button className="secondary-btn" onClick={signOut}>Sign out</button>
          </div>
        </header>

        {notice && <p className="notice error" role="alert">{notice}</p>}
        {page === 'Dashboard' && <Dashboard token={token} />}
        {page === 'POS' && <PointOfSale token={token} />}
        {page === 'Sales' && <Sales token={token} />}
        {page === 'Inventory' && <Inventory token={token} role={user.role} />}
        {page === 'Expenses' && <Expenses token={token} />}
        {page === 'Users' && <Users token={token} role={user.role} />}
      </main>
    </div>
  );
}

function useLoad(load, dependencies) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);

  async function refresh() {
    setBusy(true);
    setError('');
    try {
      setData(await load());
    } catch (reason) {
      setError(reason.message || 'Unable to load data.');
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { refresh(); }, dependencies);
  return { data, error, busy, refresh, setData };
}

function LoadState({ busy, error, children }) {
  if (busy) return <div className="empty-state">Loading from the shared POS…</div>;
  if (error) return <div className="notice error" role="alert">{error}</div>;
  return children;
}

function StatCard({ label, value, detail, accent }) {
  return <article className={`stat-card ${accent || ''}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

function Dashboard({ token }) {
  const { data, error, busy } = useLoad(async () => {
    const [summary, products, sales] = await Promise.all([
      request('/dashboard/summary', token),
      request('/products', token),
      request('/sales', token),
    ]);
    return { summary, products, sales };
  }, [token]);

  return (
    <LoadState busy={busy} error={error}>
      {data && <>
        <section className="stats-grid">
          <StatCard label="Sales recorded" value={data.summary.total_sales} detail="Transactions on this account" />
          <StatCard label="Sales revenue" value={money(data.summary.total_revenue)} detail="Confirmed cash sales" accent="gold" />
          <StatCard label="Products" value={data.summary.total_products} detail="Active catalog" />
          <StatCard label="Low stock" value={data.summary.low_stock} detail="At or below reorder level" accent={data.summary.low_stock ? 'warning' : ''} />
        </section>
        <section className="panel-grid">
          <div className="panel">
            <div className="panel-heading"><div><p className="eyebrow">RESTOCK ATTENTION</p><h2>Low stock</h2></div><span className="pill">{data.products.filter((product) => product.stock_quantity <= product.reorder_level).length} items</span></div>
            <ProductTable products={data.products.filter((product) => product.stock_quantity <= product.reorder_level)} />
          </div>
          <div className="panel">
            <div className="panel-heading"><div><p className="eyebrow">LATEST ACTIVITY</p><h2>Recent sales</h2></div></div>
            <SalesTable sales={data.sales.slice(0, 6)} />
          </div>
        </section>
      </>}
    </LoadState>
  );
}

function PointOfSale({ token }) {
  const { data: products, error, busy, refresh } = useLoad(() => request('/products', token), [token]);
  const [search, setSearch] = useState('');
  const [cart, setCart] = useState([]);
  const [message, setMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const total = cart.reduce((sum, item) => sum + Number(item.selling_price) * item.quantity, 0);
  const filtered = useMemo(() => (products || []).filter((product) => (
    `${product.name} ${product.sku} ${product.category}`.toLowerCase().includes(search.toLowerCase())
  )), [products, search]);

  function add(product) {
    setMessage('');
    if (product.stock_quantity < 1) return setMessage(`${product.name} is out of stock.`);
    const existing = cart.find((item) => item.id === product.id);
    if (existing && existing.quantity >= product.stock_quantity) {
      setMessage(`Only ${product.stock_quantity} ${product.unit || 'units'} of ${product.name} are available.`);
      return;
    }
    setCart((items) => {
      return existing
        ? items.map((item) => item.id === product.id ? { ...item, quantity: item.quantity + 1 } : item)
        : [...items, { ...product, quantity: 1 }];
    });
  }

  function changeQuantity(id, amount) {
    setCart((items) => items.map((item) => item.id === id
      ? { ...item, quantity: Math.min(item.stock_quantity, Math.max(0, item.quantity + amount)) }
      : item).filter((item) => item.quantity > 0));
  }

  async function checkout() {
    if (!cart.length || submitting) return;
    setSubmitting(true);
    setMessage('');
    try {
      const result = await request('/sales', token, {
        method: 'POST',
        body: JSON.stringify({
          payment_method: 'cash',
          items: cart.map((item) => ({ product_id: item.id, quantity: item.quantity })),
        }),
      });
      setMessage(`Sale ${result.sale_number} completed for ${money(result.total)}.`);
      setCart([]);
      await refresh();
    } catch (reason) {
      setMessage(reason.message || 'Checkout failed. The cart has been kept.');
    } finally {
      setSubmitting(false);
    }
  }

  if (!products && busy) return <div className="empty-state">Loading products from the shared POS…</div>;
  if (!products) return <div className="notice error" role="alert">{error || 'Unable to load products.'}<button className="secondary-btn" onClick={refresh}>Retry</button></div>;

  return (
    <>
      {error && <p className="notice error" role="alert">Sale data may be stale: {error} <button className="secondary-btn" onClick={refresh}>Retry</button></p>}
      <div className="pos-layout">
        <section className="panel catalog-panel">
          <div className="panel-heading"><div><p className="eyebrow">PRODUCT CATALOG</p><h2>Select items</h2></div><span className="pill">{filtered.length} products</span></div>
          <input className="search-input" placeholder="Search name, SKU or category…" value={search} onChange={(event) => setSearch(event.target.value)} />
          <div className="catalog-grid">
            {filtered.map((product) => (
              <button className="catalog-item" key={product.id} disabled={product.stock_quantity < 1} onClick={() => add(product)}>
                <span className="catalog-category">{product.category}</span>
                <strong>{product.name}</strong>
                <span>{product.sku}</span>
                <div><b>{money(product.selling_price)}</b><small>{product.stock_quantity} in stock</small></div>
              </button>
            ))}
            {!filtered.length && <p className="empty-state">No matching products.</p>}
          </div>
        </section>
        <section className="panel cart-panel">
          <div className="panel-heading"><div><p className="eyebrow">CURRENT TRANSACTION</p><h2>Cart <span className="cart-count">{cart.reduce((sum, item) => sum + item.quantity, 0)}</span></h2></div></div>
          <div className="cart-lines">
            {cart.map((item) => <div className="cart-line" key={item.id}>
              <div className="cart-name"><strong>{item.name}</strong><small>{money(item.selling_price)} each</small></div>
              <div className="quantity-control">
                <button aria-label={`Decrease ${item.name}`} onClick={() => changeQuantity(item.id, -1)}>−</button>
                <span>{item.quantity}</span>
                <button aria-label={`Increase ${item.name}`} disabled={item.quantity >= item.stock_quantity} onClick={() => changeQuantity(item.id, 1)}>+</button>
              </div>
              <strong>{money(item.selling_price * item.quantity)}</strong>
            </div>)}
            {!cart.length && <div className="empty-state">Your cart is empty.<br />Select a product to get started.</div>}
          </div>
          <div className="checkout">
            <label>Payment method<select value="cash" disabled><option value="cash">Cash · available</option><option disabled>M-Pesa · provider setup required</option><option disabled>Card · provider setup required</option></select></label>
            <div className="total-line"><span>Total due</span><strong>{money(total)}</strong></div>
            {message && <p className={`notice ${message.startsWith('Sale ') ? 'success' : 'error'}`} role="status">{message}</p>}
            <button className="primary-btn full-width" onClick={checkout} disabled={!cart.length || submitting}>{submitting ? 'Processing…' : 'Complete cash sale'}</button>
            <small className="muted">Inventory is deducted after the server confirms the sale.</small>
          </div>
        </section>
      </div>
    </>
  );
}

function ProductTable({ products }) {
  if (!products.length) return <div className="empty-state">No products need attention.</div>;
  return <div className="table-scroll"><table><thead><tr><th>Product</th><th>SKU</th><th>On hand</th><th>Reorder at</th></tr></thead><tbody>
    {products.map((product) => <tr key={product.id}><td>{product.name}</td><td>{product.sku}</td><td><span className="stock-low">{product.stock_quantity}</span></td><td>{product.reorder_level}</td></tr>)}
  </tbody></table></div>;
}

function SalesTable({ sales }) {
  if (!sales.length) return <div className="empty-state">No sales recorded yet.</div>;
  return <div className="table-scroll"><table><thead><tr><th>Receipt</th><th>Date</th><th>Payment</th><th>Total</th></tr></thead><tbody>
    {sales.map((sale) => <tr key={sale.id}><td>{sale.sale_number}</td><td>{sale.sale_time ? new Date(sale.sale_time).toLocaleString() : '—'}</td><td><span className="pill">{sale.payment_method}</span></td><td>{money(sale.total)}</td></tr>)}
  </tbody></table></div>;
}

function Sales({ token }) {
  const { data: sales, error, busy, refresh } = useLoad(() => request('/sales', token), [token]);
  return <section className="panel">
    <div className="panel-heading"><div><p className="eyebrow">TRANSACTION HISTORY</p><h2>Sales</h2></div><button className="secondary-btn" onClick={refresh}>Refresh</button></div>
    <LoadState busy={busy} error={error}>{sales && <SalesTable sales={sales} />}</LoadState>
  </section>;
}

function Inventory({ token, role }) {
  const { data: products, error, busy, refresh } = useLoad(() => request('/inventory', token), [token]);
  const [selectedId, setSelectedId] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);
  const canManageProducts = role === 'owner' || role === 'manager';
  const [newProduct, setNewProduct] = useState({ sku: '', name: '', category: '', buying_price: '', selling_price: '', stock_quantity: '0', reorder_level: '5' });

  async function receiveStock(event) {
    event.preventDefault();
    setSaving(true);
    setNotice('');
    try {
      await request('/inventory/movement', token, {
        method: 'POST',
        body: JSON.stringify({ product_id: Number(selectedId), quantity: Number(quantity), type: 'receive', note: 'Stock received' }),
      });
      setNotice('Stock received and inventory updated.');
      await refresh();
    } catch (reason) {
      setNotice(reason.message);
    } finally {
      setSaving(false);
    }
  }

  async function createProduct(event) {
    event.preventDefault();
    setSaving(true);
    setNotice('');
    try {
      await request('/products', token, {
        method: 'POST',
        body: JSON.stringify({
          ...newProduct,
          unit: 'unit',
          buying_price: Number(newProduct.buying_price),
          selling_price: Number(newProduct.selling_price),
          stock_quantity: Number(newProduct.stock_quantity),
          reorder_level: Number(newProduct.reorder_level),
        }),
      });
      setNotice('Product added to the shared catalog.');
      setNewProduct({ sku: '', name: '', category: '', buying_price: '', selling_price: '', stock_quantity: '0', reorder_level: '5' });
      await refresh();
    } catch (reason) {
      setNotice(reason.message);
    } finally {
      setSaving(false);
    }
  }

  return <div className="stack">
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">SHARED PRODUCT CATALOG</p><h2>Inventory</h2></div><button className="secondary-btn" onClick={refresh}>Refresh</button></div>
      <LoadState busy={busy} error={error}>{products && <ProductTable products={products} />}</LoadState>
    </section>
    <div className="form-grid">
      <section className="panel">
        <p className="eyebrow">STOCK CONTROL</p><h2>Receive stock</h2>
        <form className="form-stack" onSubmit={receiveStock}>
          <label>Product<select required value={selectedId} onChange={(event) => setSelectedId(event.target.value)}><option value="">Select a product</option>{(products || []).map((product) => <option value={product.id} key={product.id}>{product.name} · {product.stock_quantity} on hand</option>)}</select></label>
          <label>Quantity<input type="number" min="1" step="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} required /></label>
          <button className="primary-btn" disabled={saving || !selectedId}>{saving ? 'Saving…' : 'Record stock received'}</button>
        </form>
      </section>
      {canManageProducts && <section className="panel">
        <p className="eyebrow">CATALOG MANAGEMENT</p><h2>Add a product</h2>
        <form className="form-stack two-column-form" onSubmit={createProduct}>
          {[
            ['sku', 'SKU', 'text'], ['name', 'Product name', 'text'], ['category', 'Category', 'text'],
            ['buying_price', 'Buying price (KSh)', 'number'], ['selling_price', 'Selling price (KSh)', 'number'],
            ['stock_quantity', 'Opening stock', 'number'], ['reorder_level', 'Reorder level', 'number'],
          ].map(([field, label, type]) => <label key={field}>{label}<input type={type} min={type === 'number' ? '0' : undefined} step={field === 'stock_quantity' || field === 'reorder_level' ? '1' : type === 'number' ? '0.01' : undefined} required value={newProduct[field]} onChange={(event) => setNewProduct({ ...newProduct, [field]: event.target.value })} /></label>)}
          <button className="primary-btn" disabled={saving}>{saving ? 'Saving…' : 'Add product'}</button>
        </form>
      </section>}
    </div>
    {notice && <p className={`notice ${notice.startsWith('Stock received') || notice.startsWith('Product added') ? 'success' : 'error'}`} role="status">{notice}</p>}
  </div>;
}

function Expenses({ token }) {
  const { data: expenses, error, busy, refresh } = useLoad(() => request('/expenses', token), [token]);
  const [form, setForm] = useState({ description: '', category: '', amount: '', payment_method: 'cash' });
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setNotice('');
    try {
      await request('/expenses', token, {
        method: 'POST',
        body: JSON.stringify({ ...form, amount: Number(form.amount) }),
      });
      setNotice('Expense recorded.');
      setForm({ description: '', category: '', amount: '', payment_method: 'cash' });
      await refresh();
    } catch (reason) {
      setNotice(reason.message);
    } finally {
      setSaving(false);
    }
  }

  return <div className="form-grid">
    <section className="panel"><p className="eyebrow">BUSINESS COSTS</p><h2>Record an expense</h2>
      <form className="form-stack" onSubmit={submit}>
        <label>Description<input value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} required /></label>
        <label>Category<input value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} /></label>
        <label>Amount (KSh)<input type="number" min="0.01" step="0.01" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} required /></label>
        <label>Payment method<select value={form.payment_method} onChange={(event) => setForm({ ...form, payment_method: event.target.value })}><option value="cash">Cash</option><option value="mpesa">M-Pesa</option><option value="card">Card</option></select></label>
        <button className="primary-btn" disabled={saving}>{saving ? 'Saving…' : 'Save expense'}</button>
      </form>
      {notice && <p className="notice" role="status">{notice}</p>}
    </section>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">RECENT COSTS</p><h2>Expenses</h2></div><button className="secondary-btn" onClick={refresh}>Refresh</button></div>
      <LoadState busy={busy} error={error}>{expenses?.length ? <div className="table-scroll"><table><thead><tr><th>Description</th><th>Category</th><th>Amount</th><th>Date</th></tr></thead><tbody>{expenses.map((expense) => <tr key={expense.id}><td>{expense.description}</td><td>{expense.category}</td><td>{money(expense.amount)}</td><td>{expense.created_at ? new Date(expense.created_at).toLocaleDateString() : '—'}</td></tr>)}</tbody></table></div> : <div className="empty-state">No expenses recorded.</div>}</LoadState>
    </section>
  </div>;
}

function Users({ token, role }) {
  const { data: users, error, busy, refresh } = useLoad(() => request('/users', token), [token]);
  const [form, setForm] = useState({ username: '', full_name: '', email: '', password: '', role: 'cashier' });
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setNotice('');
    try {
      await request('/users', token, { method: 'POST', body: JSON.stringify(form) });
      setNotice('Staff account created.');
      setForm({ username: '', full_name: '', email: '', password: '', role: 'cashier' });
      await refresh();
    } catch (reason) {
      setNotice(reason.message);
    } finally {
      setSaving(false);
    }
  }

  return <div className="form-grid">
    <section className="panel"><p className="eyebrow">STAFF ACCESS</p><h2>Create a staff account</h2>
      <form className="form-stack" onSubmit={submit}>
        <label>Full name<input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} required /></label>
        <label>Username<input autoComplete="off" value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} required /></label>
        <label>Email<input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required /></label>
        <label>Temporary password<input type="password" minLength="6" autoComplete="new-password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required /></label>
        <label>Role<select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}><option value="cashier">Cashier</option><option value="stock">Stock</option>{role === 'owner' && <option value="manager">Manager</option>}</select></label>
        <button className="primary-btn" disabled={saving}>{saving ? 'Creating…' : 'Create account'}</button>
      </form>
      {notice && <p className="notice" role="status">{notice}</p>}
    </section>
    <section className="panel"><div className="panel-heading"><div><p className="eyebrow">TEAM</p><h2>Staff accounts</h2></div><button className="secondary-btn" onClick={refresh}>Refresh</button></div>
      <LoadState busy={busy} error={error}>{users?.length ? <div className="table-scroll"><table><thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Status</th></tr></thead><tbody>{users.map((staff) => <tr key={staff.id}><td>{staff.full_name}</td><td>{staff.username}</td><td>{staff.role}</td><td>{staff.is_active ? 'Active' : 'Inactive'}</td></tr>)}</tbody></table></div> : <div className="empty-state">No staff accounts found.</div>}</LoadState>
    </section>
  </div>;
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><App /></React.StrictMode>,
);
