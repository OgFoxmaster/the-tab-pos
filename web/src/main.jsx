import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom/client';
import './style.css';
import './app.css';
import { api } from './api.js';
import {
  applyLocalStock,
  cacheProducts,
  cachedProducts,
  pendingSales,
  queueSale,
  syncPending,
} from './offline.js';

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js').catch((error) => {
      console.error('Unable to register the POS app service worker.', error);
    });
  });
}

const FALLBACK_META = {
  store: 'The Tab',
  tagline: 'Liquor Store',
  address: 'Nairobi, Kenya',
  phone: '+254 700 000 000',
  currency: 'KES',
  receipt_footer: 'Thank you for shopping with The Tab. Drink responsibly.',
  vat_rate: 0.16,
  mpesa_enabled: false,
  mpesa_simulate: false,
};

const ROLE_PAGES = {
  owner: ['Dashboard', 'POS', 'Sales', 'Reports', 'Insights', 'Inventory', 'Expenses', 'Users'],
  manager: ['Dashboard', 'POS', 'Sales', 'Reports', 'Insights', 'Inventory', 'Expenses', 'Users'],
  stock: ['Inventory'],
  cashier: ['Dashboard', 'POS', 'Sales'],
};

const PAGE_ICONS = {
  Dashboard: '◫',
  POS: '＋',
  Sales: '▤',
  Reports: '◑',
  Insights: '✦',
  Inventory: '▦',
  Expenses: '↗',
  Users: '♙',
};

function money(value) {
  return `KSh ${Number(value || 0).toLocaleString('en-KE', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function compactMoney(value) {
  return `KSh ${Number(value || 0).toLocaleString('en-KE', { maximumFractionDigits: 0 })}`;
}

function formatDate(value, withTime = false) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return withTime ? date.toLocaleString() : date.toLocaleDateString();
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function newReference() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  return `off-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function readStoredUser() {
  try {
    return JSON.parse(sessionStorage.getItem('tabpos.user') || 'null');
  } catch {
    return null;
  }
}

function useLoad(load, dependencies) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);

  const refresh = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      setData(await load());
    } catch (reason) {
      setError(reason.message || 'Unable to load data.');
    } finally {
      setBusy(false);
    }
  }, dependencies);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, error, busy, refresh, setData };
}

function LoadState({ busy, error, children }) {
  if (busy) return <div className="empty-state">Loading from the shared POS…</div>;
  if (error) return <div className="notice error" role="alert">{error}</div>;
  return children;
}

function StatCard({ label, value, detail, accent }) {
  return (
    <article className={`stat-card ${accent || ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function Modal({ title, eyebrow, children, onClose, wide }) {
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <div className={`modal ${wide ? 'wide' : ''}`}>
        <div className="modal-head">
          <div>
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            <h2>{title}</h2>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">×</button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Login({ onLogin }) {
  const params = new URLSearchParams(window.location.search);
  const [mode, setMode] = useState(() => (params.get('reset') ? 'reset' : 'signin'));
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [phone, setPhone] = useState('');
  const [loginCode, setLoginCode] = useState('');
  const [loginChallenge, setLoginChallenge] = useState('');
  const [loginStep, setLoginStep] = useState(false);
  const [fullName, setFullName] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [branchName, setBranchName] = useState('Main Branch');
  const [branchAddress, setBranchAddress] = useState('');
  const [email, setEmail] = useState('');
  const [signupCode, setSignupCode] = useState('');
  const [token, setToken] = useState(() => params.get('reset') || '');
  const [confirm, setConfirm] = useState('');
  const [setup, setSetup] = useState(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.setupStatus().then(setSetup).catch(() => setSetup(null));
  }, []);

  const signupOpen = setup?.signup_open !== false;

  async function finishLogin(result) {
    const user = await api.me(result.access_token);
    onLogin(result.access_token, user);
  }

  function switchMode(next) {
    setMode(next);
    setError('');
    setNotice('');
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setNotice('');
    try {
      if (mode === 'signin') {
        const result = await api.login(username.trim(), password, loginStep ? loginCode.trim() : undefined, loginStep ? loginChallenge : undefined);
        if (result.requires_login_code) {
          setLoginStep(true);
          setLoginChallenge(result.login_challenge);
          setNotice(result.dev_login_code ? `Development login code: ${result.dev_login_code}` : `A login code was sent by ${result.login_code_channel || 'your configured channel'}.`);
        } else {
          await finishLogin(result);
        }
      } else if (mode === 'signup') {
        if (password.length < 8) throw new Error('Use at least 8 characters for the password.');
        const result = await api.registerOwner({
          company_name: companyName.trim(),
          branch_name: branchName.trim(),
          branch_address: branchAddress.trim() || undefined,
          full_name: fullName.trim(),
          email: email.trim(),
          phone: phone.trim() || undefined,
          password,
          signup_code: signupCode.trim() || undefined,
        });
        await finishLogin(result);
      } else if (mode === 'forgot') {
        const result = await api.forgotPassword(email.trim(), phone.trim());
        setNotice(result.message);
        if (result.dev_reset_token) {
          setToken(result.dev_reset_token);
          setNotice(`${result.message} Email is not configured yet, so use the development reset form below.`);
        }
      } else if (mode === 'reset') {
        if (password.length < 8) throw new Error('Use at least 8 characters for the new password.');
        if (password !== confirm) throw new Error('The two passwords do not match.');
        const result = await api.resetPassword(token.trim(), password);
        setNotice(result.message);
        setMode('signin');
        setLoginStep(false);
        setLoginCode('');
        setLoginChallenge('');
        setPassword('');
        setConfirm('');
        setToken('');
        window.history.replaceState({}, '', window.location.pathname);
      }
    } catch (reason) {
      setError(reason.message || 'The request could not be completed.');
    } finally {
      setBusy(false);
    }
  }

  const headings = {
    signin: ['Welcome back', loginStep ? 'Enter the one-time code sent to your email or phone.' : 'Sign in with your staff account to continue.'],
    signup: ['Create your company account', 'Register your company and first branch. You will become its owner and can invite employees later.'],
    forgot: ['Forgot your password?', 'Enter the email or registered phone number on your account and we will send a reset code or link.'],
    reset: ['Choose a new password', 'This reset link works once and expires automatically.'],
  };
  const [title, subtitle] = headings[mode];
  const actionLabel = {
    signin: loginStep ? 'Verify and sign in' : 'Sign in',
    signup: 'Create owner account',
    forgot: 'Send reset code',
    reset: 'Update password',
  }[mode];

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={submit}>
        <div className="brand-mark">T</div>
        <p className="eyebrow">THE TAB · LIQUOR STORE</p>
        <h1>{title}</h1>
        <p className="muted">{subtitle}</p>

        {(mode === 'signin' || mode === 'signup') && (
          <div className="login-tabs" role="tablist">
            <button type="button" className={mode === 'signin' ? 'active' : ''} onClick={() => switchMode('signin')}>Sign in</button>
            {signupOpen && (
              <button type="button" className={mode === 'signup' ? 'active' : ''} onClick={() => switchMode('signup')}>Create owner account</button>
            )}
          </div>
        )}

        {mode === 'signup' && (
          <label>Company name
            <input value={companyName} onChange={(event) => setCompanyName(event.target.value)} placeholder="Acme Retail Ltd" required />
          </label>
        )}

        {mode === 'signup' && (
          <label>First branch
            <input value={branchName} onChange={(event) => setBranchName(event.target.value)} placeholder="Main Branch" required />
          </label>
        )}

        {mode === 'signup' && (
          <label>Branch address (optional)
            <input value={branchAddress} onChange={(event) => setBranchAddress(event.target.value)} placeholder="Nairobi CBD" />
          </label>
        )}

        {mode === 'signup' && (
          <label>Owner name
            <input autoComplete="name" value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="Jane Wanjiku" required />
          </label>
        )}

        {(mode === 'signup' || mode === 'forgot') && (
          <label>{mode === 'forgot' ? 'Email address (or leave blank for phone reset)' : 'Email address'}
            <input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@gmail.com" required={mode === 'signup'} />
          </label>
        )}

        {(mode === 'signup' || mode === 'forgot') && (
          <label>{mode === 'forgot' ? 'Registered phone number (or leave blank for email reset)' : 'Phone number (optional for signup)'}
            <input type="tel" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="0712 345 678" required={false} />
          </label>
        )}

        {mode === 'signin' && (
          <label>Username
            <input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required />
          </label>
        )}

        {mode === 'reset' && !token && (
          <label>Reset token
            <input value={token} onChange={(event) => setToken(event.target.value)} required />
          </label>
        )}

        {mode === 'signin' && loginStep && (
          <label>One-time login code
            <input inputMode="numeric" autoComplete="one-time-code" value={loginCode} onChange={(event) => setLoginCode(event.target.value)} required />
          </label>
        )}

        {(mode === 'signin' || mode === 'signup' || mode === 'reset') && (
          <label>{mode === 'reset' ? 'New password' : 'Password'}
            <input
              type="password"
              autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={mode === 'signin' ? 1 : 8}
              required
            />
          </label>
        )}

        {mode === 'reset' && (
          <label>Confirm new password
            <input type="password" autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} minLength={8} required />
          </label>
        )}

        {mode === 'signup' && setup?.requires_code && (
          <label>Owner signup code
            <input value={signupCode} onChange={(event) => setSignupCode(event.target.value)} required />
          </label>
        )}

        {notice && <p className="notice success" role="status">{notice}</p>}
        {error && <p className="notice error" role="alert">{error}</p>}

        <button className="primary-btn full-width" disabled={busy}>
          {busy ? 'Please wait…' : actionLabel}
        </button>

        {mode === 'forgot' && token && (
          <button type="button" className="secondary-btn full-width" onClick={() => switchMode('reset')}>Open the reset form</button>
        )}

        {mode === 'signin' && (
          <p className="login-links">
            <button type="button" className="link-btn" onClick={() => switchMode('forgot')}>Forgot password?</button>
          </p>
        )}
        {mode !== 'signin' && (
          <p className="login-links">
            <button type="button" className="link-btn" onClick={() => switchMode('signin')}>← Back to sign in</button>
          </p>
        )}

        {mode === 'signin' && setup && !setup.signup_open && (
          <p className="login-footnote">The owner account already exists. Ask the owner to create your staff login from the Users page.</p>
        )}
        {mode === 'signin' && (
          <p className="login-footnote">An internet connection is required to sign in. The till keeps selling offline once signed in.</p>
        )}
      </form>
    </main>
  );
}

function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem('tabpos.token') || '');
  const [user, setUser] = useState(readStoredUser);
  const [page, setPage] = useState('');
  const [notice, setNotice] = useState('');
  const [meta, setMeta] = useState(FALLBACK_META);
  const [pending, setPending] = useState(0);
  const [syncNotice, setSyncNotice] = useState('');
  const [online, setOnline] = useState(() => navigator.onLine);

  const refreshPending = useCallback(async () => {
    setPending((await pendingSales()).length);
  }, []);

  const sync = useCallback(async (activeToken) => {
    if (!activeToken || !navigator.onLine) return;
    if (!(await pendingSales()).length) return;
    const result = await syncPending(activeToken);
    setPending(result.remaining);
    if (result.synced > 0) {
      setSyncNotice(`${result.synced} offline sale${result.synced === 1 ? '' : 's'} synced to the shared POS.`);
    }
    if (result.errors?.length) {
      setSyncNotice(`One offline sale needs attention: ${result.errors[0]}`);
    }
  }, []);

  useEffect(() => {
    if (!token) return;
    api.me(token)
      .then((currentUser) => {
        setUser(currentUser);
        sessionStorage.setItem('tabpos.user', JSON.stringify(currentUser));
        return api.meta();
      })
      .then((storeMeta) => setMeta(storeMeta))
      .catch((error) => {
        if (error.status === 401) signOut();
        else setNotice(error.message);
      });
  }, [token]);

  useEffect(() => {
    if (!token) return undefined;
    refreshPending();
    sync(token);

    const interval = setInterval(() => sync(token), 30000);
    const goOnline = () => {
      setOnline(true);
      sync(token);
      refreshPending();
    };
    const goOffline = () => setOnline(false);

    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => {
      clearInterval(interval);
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, [token, sync, refreshPending]);

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
          <span><strong>{meta.store}</strong><small>POINT OF SALE</small></span>
        </a>
        <p className="nav-caption">WORKSPACE</p>
        <nav aria-label="Main navigation">
          {pages.map((item) => (
            <button
              key={item}
              className={`nav-item ${page === item ? 'active' : ''}`}
              onClick={() => { setPage(item); setNotice(''); setSyncNotice(''); }}
            >
              <span className="nav-icon">{PAGE_ICONS[item]}</span>
              {item}
              {item === 'POS' && pending > 0 && <span className="nav-badge">{pending}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className={`status-dot ${online ? '' : 'offline'}`} />
          {online ? 'Connected to shared POS' : 'Offline — sales are queued'}
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div>
            <p className="eyebrow">{meta.store.toUpperCase()} POS / {user.role.toUpperCase()}</p>
            <h1>{page}</h1>
          </div>
          <div className="profile">
            <div className="avatar">{(user.full_name || user.username || '?').slice(0, 1).toUpperCase()}</div>
            <div className="profile-name"><strong>{user.full_name || user.username}</strong><small>{user.role}</small></div>
            <button className="secondary-btn" onClick={signOut}>Sign out</button>
          </div>
        </header>

        {!online && (
          <p className="notice warning" role="status">
            This till is offline. Keep selling cash sales — they are saved on this device and sync automatically.
            {pending > 0 ? ` ${pending} sale${pending === 1 ? '' : 's'} waiting to sync.` : ''}
          </p>
        )}
        {syncNotice && <p className="notice success" role="status">{syncNotice}</p>}
        {notice && <p className="notice error" role="alert">{notice}</p>}

        {page === 'Dashboard' && <Dashboard token={token} meta={meta} pending={pending} />}
        {page === 'POS' && (
          <PointOfSale token={token} meta={meta} online={online} onQueued={refreshPending} />
        )}
        {page === 'Sales' && <Sales token={token} role={user.role} meta={meta} />}
        {page === 'Reports' && <Reports token={token} meta={meta} />}
        {page === 'Insights' && <Insights token={token} meta={meta} />}
        {page === 'Inventory' && <Inventory token={token} role={user.role} />}
        {page === 'Expenses' && <Expenses token={token} />}
        {page === 'Users' && <Users token={token} role={user.role} />}
      </main>
    </div>
  );
}

function Dashboard({ token, meta, pending }) {
  const { data, error, busy } = useLoad(async () => {
    const [summary, products, sales] = await Promise.all([
      api.dashboard(token),
      api.products(token),
      api.sales(token, { limit: 6 }),
    ]);
    return { summary, products, sales };
  }, [token]);

  const lowStock = useMemo(
    () => (data?.products || []).filter((product) => product.stock_quantity <= product.reorder_level),
    [data],
  );

  return (
    <LoadState busy={busy} error={error}>
      {data && (
        <>
          <section className="stats-grid">
            <StatCard label="Revenue today" value={compactMoney(data.summary.today_revenue)} detail={`${data.summary.today_transactions} sale(s) today`} accent="gold" />
            <StatCard label="Revenue on this account" value={compactMoney(data.summary.total_revenue)} detail={`${data.summary.total_sales} transactions`} />
            <StatCard label="Products" value={data.summary.total_products} detail="Active catalog" />
            <StatCard label="Low stock" value={data.summary.low_stock} detail="At or below reorder level" accent={data.summary.low_stock ? 'warning' : ''} />
          </section>

          {pending > 0 && (
            <p className="notice warning" role="status">
              {pending} offline sale{pending === 1 ? '' : 's'} waiting to sync from this till.
            </p>
          )}

          <section className="panel-grid">
            <div className="panel">
              <div className="panel-heading">
                <div><p className="eyebrow">RESTOCK ATTENTION</p><h2>Low stock</h2></div>
                <span className="pill">{lowStock.length} items</span>
              </div>
              <ProductTable products={lowStock} />
            </div>
            <div className="panel">
              <div className="panel-heading"><div><p className="eyebrow">LATEST ACTIVITY</p><h2>Recent sales</h2></div></div>
              <SalesTable sales={data.sales} meta={meta} />
            </div>
          </section>
        </>
      )}
    </LoadState>
  );
}

function ProductTable({ products }) {
  if (!products.length) return <div className="empty-state">No products need attention.</div>;
  return (
    <div className="table-scroll">
      <table>
        <thead><tr><th>Product</th><th>SKU</th><th>On hand</th><th>Reorder at</th></tr></thead>
        <tbody>
          {products.map((product) => (
            <tr key={product.id}>
              <td>{product.name}</td>
              <td>{product.sku}</td>
              <td><span className="stock-low">{product.stock_quantity}</span></td>
              <td>{product.reorder_level}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SalesTable({ sales, meta, onOpen }) {
  if (!sales.length) return <div className="empty-state">No sales recorded yet.</div>;
  return (
    <div className="table-scroll">
      <table>
        <thead><tr><th>Receipt</th><th>Date</th><th>Payment</th><th>Total</th>{onOpen && <th />}</tr></thead>
        <tbody>
          {sales.map((sale) => (
            <tr key={sale.id}>
              <td>
                {sale.sale_number}
                {sale.payment_status === 'refunded' && <span className="badge danger">refunded</span>}
                {sale.offline && <span className="badge">offline</span>}
              </td>
              <td>{formatDate(sale.sale_time, true)}</td>
              <td><span className="pill">{sale.payment_method}</span></td>
              <td>{money(sale.total)}</td>
              {onOpen && <td><button className="link-btn" onClick={() => onOpen(sale)}>Receipt</button></td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReceiptModal({ receipt, meta, onClose }) {
  if (!receipt) return null;
  const total = Number(receipt.total) || 0;
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Receipt">
      <div className="receipt">
        <div className="receipt-brand">
          <div className="brand-mark small">T</div>
          <div><strong>{meta.store}</strong><small>{meta.tagline}</small></div>
        </div>
        <p className="receipt-meta">{meta.address} · {meta.phone}</p>
        <div className="receipt-meta-row">
          <span>{receipt.number}</span>
          <span>{formatDate(receipt.at, true)}</span>
        </div>
        {receipt.cashier && <p className="receipt-meta">Served by {receipt.cashier}</p>}
        {receipt.customer && <p className="receipt-meta">Customer: {receipt.customer}</p>}
        {receipt.payment_method && (
          <p className="receipt-meta">
            Paid by {receipt.payment_method === 'mpesa' ? 'M-Pesa' : 'Cash'}
            {receipt.mpesa_receipt ? ` · ${receipt.mpesa_receipt}` : ''}
          </p>
        )}
        {receipt.offline && <p className="receipt-offline">Offline receipt — syncs when the till reconnects</p>}

        <table className="receipt-items">
          <thead><tr><th>Item</th><th>Qty</th><th>Amount</th></tr></thead>
          <tbody>
            {(receipt.items || []).map((item, index) => (
              <tr key={`${item.name}-${index}`}>
                <td>{item.name}</td>
                <td>{item.quantity}</td>
                <td>{money(item.total ?? item.unit_price * item.quantity)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="receipt-totals">
          <div><span>Subtotal</span><span>{money(receipt.subtotal)}</span></div>
          {Number(receipt.discount) > 0 && (
            <div><span>Discount</span><span>−{money(receipt.discount)}</span></div>
          )}
          <div><span>VAT included</span><span>{money(receipt.vat)}</span></div>
          <div className="receipt-total"><span>Total</span><span>{money(total)}</span></div>
          {receipt.tendered != null && <div><span>Cash received</span><span>{money(receipt.tendered)}</span></div>}
          {receipt.change > 0 && <div><span>Change</span><span>{money(receipt.change)}</span></div>}
        </div>

        <p className="receipt-footer">{meta.receipt_footer}</p>
        <div className="receipt-actions no-print">
          <button className="secondary-btn" onClick={onClose}>Close</button>
          <button className="primary-btn" onClick={() => window.print()}>Print receipt</button>
        </div>
      </div>
    </div>
  );
}

function PointOfSale({ token, meta, online, onQueued }) {
  const [products, setProducts] = useState(null);
  const [source, setSource] = useState('network');
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [scan, setScan] = useState('');
  const [cart, setCart] = useState([]);
  const [discount, setDiscount] = useState('');
  const [customer, setCustomer] = useState('');
  const [tendered, setTendered] = useState('');
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);
  const [receipt, setReceipt] = useState(null);
  const [method, setMethod] = useState('cash');
  const [phone, setPhone] = useState('');
  const [intent, setIntent] = useState(null);
  const [paymentBusy, setPaymentBusy] = useState(false);
  const [draft, setDraft] = useState(null);
  const mpesaEnabled = Boolean(meta.mpesa_enabled);
  const mpesaSimulate = Boolean(meta.mpesa_simulate);

  const load = useCallback(async () => {
    try {
      const data = await api.products(token);
      setProducts(data);
      setSource('network');
      setError('');
      await cacheProducts(data);
    } catch (reason) {
      const cached = await cachedProducts();
      setError(reason.message);
      if (cached) {
        setProducts(cached);
        setSource('cache');
      } else {
        setProducts([]);
      }
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const settlePayment = useCallback((paid) => {
    if (!paid?.sale || !draft) return;
    setMessage({
      type: 'success',
      text: `M-Pesa payment received${paid.mpesa_receipt ? ` (${paid.mpesa_receipt})` : ''}. Sale ${paid.sale.sale_number}.`,
    });
    setReceipt({
      subtotal: draft.subtotal,
      discount: draft.discountValue,
      vat: draft.vat,
      total: draft.total,
      items: draft.lines,
      customer: draft.customer || null,
      tendered: null,
      change: 0,
      cashier: JSON.parse(sessionStorage.getItem('tabpos.user') || '{}')?.username,
      at: paid.sale.sale_time || new Date().toISOString(),
      number: paid.sale.sale_number,
      payment_method: 'mpesa',
      mpesa_receipt: paid.mpesa_receipt,
      offline: false,
    });
    setCart([]);
    setDiscount('');
    setCustomer('');
    setTendered('');
    setPhone('');
    setIntent(null);
    setDraft(null);
    load();
  }, [draft, load]);

  useEffect(() => {
    if (!intent || intent.status !== 'pending' || !online) return undefined;
    let active = true;
    const tick = async () => {
      try {
        const next = await api.paymentStatus(token, intent.reference);
        if (!active) return;
        setIntent(next);
        if (next.status === 'paid') {
          settlePayment(next);
        } else if (next.status === 'failed') {
          setMessage({ type: 'error', text: next.result_desc || 'The M-Pesa payment was not completed. You can retry.' });
        }
      } catch {
        // A network hiccup: the next poll tries again.
      }
    };
    const timer = setInterval(tick, 4000);
    return () => { active = false; clearInterval(timer); };
  }, [intent?.reference, intent?.status, online, token, settlePayment]);

  const subtotal = cart.reduce((sum, item) => sum + Number(item.selling_price) * item.quantity, 0);
  const discountValue = Math.min(Math.max(Number(discount) || 0, 0), subtotal);
  const total = Math.max(subtotal - discountValue, 0);
  const change = Number(tendered) > total ? Number(tendered) - total : 0;

  const filtered = useMemo(() => (products || []).filter((product) => (
    `${product.name} ${product.sku} ${product.category}`.toLowerCase().includes(search.toLowerCase())
  )), [products, search]);

  function add(product) {
    setMessage(null);
    if (product.stock_quantity < 1) {
      setMessage({ type: 'error', text: `${product.name} is out of stock.` });
      return;
    }
    const existing = cart.find((item) => item.id === product.id);
    if (existing && existing.quantity >= product.stock_quantity) {
      setMessage({ type: 'error', text: `Only ${product.stock_quantity} ${product.unit || 'units'} of ${product.name} are available.` });
      return;
    }
    setCart((items) => (existing
      ? items.map((item) => (item.id === product.id ? { ...item, quantity: item.quantity + 1 } : item))
      : [...items, { ...product, quantity: 1 }]));
  }

  function changeQuantity(id, amount) {
    setCart((items) => items
      .map((item) => (item.id === id
        ? { ...item, quantity: Math.min(item.stock_quantity, Math.max(0, item.quantity + amount)) }
        : item))
      .filter((item) => item.quantity > 0));
  }

  function scanProduct(event) {
    event.preventDefault();
    const code = scan.trim().toLowerCase();
    if (!code) return;
    const match = (products || []).find(
      (product) => product.sku.toLowerCase() === code || product.name.toLowerCase() === code,
    );
    if (match) {
      add(match);
      setScan('');
    } else {
      setMessage({ type: 'error', text: `No product matches “${scan.trim()}”.` });
    }
  }

  async function checkout() {
    if (!cart.length || busy) return;
    setBusy(true);
    setMessage(null);

    const lines = cart.map((item) => ({
      product_id: item.id,
      quantity: item.quantity,
      name: item.name,
      unit_price: Number(item.selling_price),
      total: Number(item.selling_price) * item.quantity,
    }));
    const vat = meta.vat_rate > 0 ? total - total / (1 + meta.vat_rate) : 0;
    const cashTendered = Number(tendered) || 0;
    const baseReceipt = {
      subtotal,
      discount: discountValue,
      vat,
      total,
      items: lines,
      customer: customer.trim() || null,
      tendered: cashTendered > 0 ? cashTendered : null,
      change,
      cashier: JSON.parse(sessionStorage.getItem('tabpos.user') || '{}')?.username,
      at: new Date().toISOString(),
    };

    try {
      const result = await api.createSale(token, {
        payment_method: 'cash',
        items: cart.map((item) => ({ product_id: item.id, quantity: item.quantity })),
        discount: discountValue,
        customer_name: customer.trim() || undefined,
      });
      setMessage({ type: 'success', text: `Sale ${result.sale_number} completed.` });
      setReceipt({ ...baseReceipt, number: result.sale_number, at: result.sale_time || baseReceipt.at, offline: false });
      setCart([]);
      setDiscount('');
      setCustomer('');
      setTendered('');
      await load();
    } catch (reason) {
      if (reason.status === 0 || !navigator.onLine) {
        const clientReference = newReference();
        const number = `OFF-${clientReference.slice(0, 8).toUpperCase()}`;
        try {
          await queueSale({
            client_reference: clientReference,
            receipt_number: number,
            sold_at: new Date().toISOString(),
            items: lines.map((item) => ({
              product_id: item.product_id,
              quantity: item.quantity,
              name: item.name,
              unit_price: item.unit_price,
            })),
            discount: discountValue,
            customer_name: customer.trim() || null,
          });
          const updated = await applyLocalStock(lines);
          if (updated) setProducts(updated);
          setMessage({ type: 'success', text: 'Saved offline. It will sync automatically when the till reconnects.' });
          setReceipt({ ...baseReceipt, number, offline: true });
          setCart([]);
          setDiscount('');
          setCustomer('');
          setTendered('');
          onQueued();
        } catch (queueError) {
          setMessage({ type: 'error', text: `Could not save the sale offline: ${queueError.message}` });
        }
      } else {
        setMessage({ type: 'error', text: reason.message || 'Checkout failed. The cart has been kept.' });
      }
    } finally {
      setBusy(false);
    }
  }

  async function startMpesa() {
    if (!cart.length || paymentBusy || intent?.status === 'pending') return;
    if (!online) {
      setMessage({ type: 'error', text: 'M-Pesa needs this till to be online. Use a cash sale while offline.' });
      return;
    }
    if (!phone.trim()) {
      setMessage({ type: 'error', text: 'Enter the customer M-Pesa phone number.' });
      return;
    }
    if (Math.round(total * 100) % 100 !== 0) {
      setMessage({ type: 'error', text: 'M-Pesa accepts whole shillings only. Adjust the discount so the total has no cents.' });
      return;
    }

    const lines = cart.map((item) => ({
      product_id: item.id,
      quantity: item.quantity,
      name: item.name,
      unit_price: Number(item.selling_price),
      total: Number(item.selling_price) * item.quantity,
    }));
    const vat = meta.vat_rate > 0 ? total - total / (1 + meta.vat_rate) : 0;

    setPaymentBusy(true);
    setMessage(null);
    try {
      const result = await api.mpesaPayment(token, {
        items: cart.map((item) => ({ product_id: item.id, quantity: item.quantity })),
        phone: phone.trim(),
        discount: discountValue,
        customer_name: customer.trim() || undefined,
      });
      setDraft({ lines, subtotal, discountValue, vat, total, customer: customer.trim() });
      setIntent(result);
      setMessage({
        type: 'info',
        text: result.simulation
          ? 'Simulation mode: mark this payment paid or failed with the buttons below.'
          : `Payment request sent to ${result.phone}. Ask the customer to approve it with their M-Pesa PIN.`,
      });
    } catch (reason) {
      setMessage({ type: 'error', text: reason.message || 'Could not start the M-Pesa payment.' });
    } finally {
      setPaymentBusy(false);
    }
  }

  async function checkMpesa() {
    if (!intent || paymentBusy) return;
    setPaymentBusy(true);
    try {
      const next = await api.verifyPayment(token, intent.reference);
      setIntent(next);
      if (next.status === 'paid') settlePayment(next);
      else if (next.status === 'failed') setMessage({ type: 'error', text: next.result_desc || 'The payment was not completed.' });
      else setMessage({ type: 'info', text: 'M-Pesa has not confirmed yet. Ask the customer to finish on their phone.' });
    } catch (reason) {
      setMessage({ type: 'error', text: reason.message || 'Could not check the payment.' });
    } finally {
      setPaymentBusy(false);
    }
  }

  async function simulateMpesa(outcome) {
    if (!intent || paymentBusy) return;
    setPaymentBusy(true);
    try {
      const next = await api.simulatePayment(token, intent.reference, outcome);
      setIntent(next);
      if (next.status === 'paid') settlePayment(next);
      else setMessage({ type: 'error', text: next.result_desc || 'Simulated payment failure.' });
    } catch (reason) {
      setMessage({ type: 'error', text: reason.message || 'Could not simulate the payment.' });
    } finally {
      setPaymentBusy(false);
    }
  }

  function startOverPayment() {
    setIntent(null);
    setDraft(null);
    setPhone('');
    setMessage(null);
  }

  if (!products) return <div className="empty-state">Loading products from the shared POS…</div>;

  return (
    <>
      {source === 'cache' && (
        <p className="notice warning" role="status">
          Showing the offline catalog cached on this till. {error}
        </p>
      )}
      <div className="pos-layout">
        <section className="panel catalog-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">PRODUCT CATALOG</p><h2>Select items</h2></div>
            <span className="pill">{filtered.length} products</span>
          </div>

          <form className="scan-row" onSubmit={scanProduct}>
            <input
              className="search-input"
              placeholder="Scan or type a SKU and press Enter…"
              value={scan}
              onChange={(event) => setScan(event.target.value)}
            />
            <button className="secondary-btn" type="submit">Add</button>
          </form>

          <input
            className="search-input"
            placeholder="Search name, SKU or category…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />

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
          <div className="panel-heading">
            <div><p className="eyebrow">CURRENT TRANSACTION</p><h2>Cart <span className="cart-count">{cart.reduce((sum, item) => sum + item.quantity, 0)}</span></h2></div>
          </div>

          <div className="cart-lines">
            {cart.map((item) => (
              <div className="cart-line" key={item.id}>
                <div className="cart-name"><strong>{item.name}</strong><small>{money(item.selling_price)} each</small></div>
                <div className="quantity-control">
                  <button aria-label={`Decrease ${item.name}`} onClick={() => changeQuantity(item.id, -1)}>−</button>
                  <span>{item.quantity}</span>
                  <button aria-label={`Increase ${item.name}`} disabled={item.quantity >= item.stock_quantity} onClick={() => changeQuantity(item.id, 1)}>+</button>
                </div>
                <strong>{money(item.selling_price * item.quantity)}</strong>
              </div>
            ))}
            {!cart.length && <div className="empty-state">Your cart is empty.<br />Select a product or scan a SKU to get started.</div>}
          </div>

          <div className="checkout">
            <div className="checkout-fields">
              <label>Customer (optional)
                <input value={customer} onChange={(event) => setCustomer(event.target.value)} placeholder="Walk-in" />
              </label>
              <label>Discount (KSh)
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={discount}
                  onChange={(event) => setDiscount(event.target.value)}
                  placeholder="0.00"
                />
              </label>
              {method === 'cash' ? (
                <label>Cash received
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={tendered}
                    onChange={(event) => setTendered(event.target.value)}
                    placeholder={total ? total.toFixed(2) : '0.00'}
                  />
                </label>
              ) : (
                <label>M-Pesa phone
                  <input
                    type="tel"
                    inputMode="tel"
                    value={phone}
                    onChange={(event) => setPhone(event.target.value)}
                    placeholder="0712 345 678"
                  />
                </label>
              )}
            </div>

            <label>Payment method
              <select
                value={method}
                onChange={(event) => { setMethod(event.target.value); setMessage(null); }}
                disabled={intent?.status === 'pending'}
              >
                <option value="cash">Cash</option>
                <option value="mpesa" disabled={!mpesaEnabled}>M-Pesa{mpesaEnabled ? '' : ' · not configured'}</option>
              </select>
            </label>
            {!mpesaEnabled && (
              <p className="checkout-hint">Add the Safaricom Daraja keys on the server to accept M-Pesa.</p>
            )}

            {intent && (
              <div className={`payment-card ${intent.status}`}>
                <div className="payment-card-head">
                  <strong>M-Pesa · {intent.status}</strong>
                  <span>{intent.reference}</span>
                </div>
                <p>Amount {money(intent.amount)} · {intent.phone}</p>
                {intent.status === 'pending' && <p>Waiting for the customer to approve on their phone…</p>}
                {intent.mpesa_receipt && <p>Receipt code: <strong>{intent.mpesa_receipt}</strong></p>}
                {intent.result_desc && <p className="muted">{intent.result_desc}</p>}
                {intent.status === 'pending' && (
                  <div className="payment-actions">
                    {mpesaSimulate ? (
                      <>
                        <button type="button" className="secondary-btn" disabled={paymentBusy} onClick={() => simulateMpesa('paid')}>Simulate paid</button>
                        <button type="button" className="secondary-btn" disabled={paymentBusy} onClick={() => simulateMpesa('failed')}>Simulate failed</button>
                      </>
                    ) : (
                      <button type="button" className="secondary-btn" disabled={paymentBusy} onClick={checkMpesa}>
                        {paymentBusy ? 'Checking…' : 'Check payment status'}
                      </button>
                    )}
                  </div>
                )}
                <button type="button" className="link-btn" onClick={startOverPayment}>Start over</button>
              </div>
            )}

            <div className="total-line"><span>Subtotal</span><strong>{money(subtotal)}</strong></div>
            {discountValue > 0 && (
              <div className="total-line small"><span>Discount</span><span>−{money(discountValue)}</span></div>
            )}
            <div className="total-line"><span>Total due</span><strong>{money(total)}</strong></div>
            {change > 0 && <div className="total-line small"><span>Change</span><span>{money(change)}</span></div>}

            {message && <p className={`notice ${message.type}`} role="status">{message.text}</p>}

            {method === 'cash' ? (
              <button className="primary-btn full-width" onClick={checkout} disabled={!cart.length || busy}>
                {busy ? 'Processing…' : online ? 'Complete cash sale' : 'Save cash sale offline'}
              </button>
            ) : (
              <button className="primary-btn full-width" onClick={startMpesa} disabled={!cart.length || paymentBusy || intent?.status === 'pending'}>
                {paymentBusy ? 'Sending…' : 'Send M-Pesa request'}
              </button>
            )}
            <small className="muted">
              {method === 'mpesa'
                ? 'The sale is recorded only after M-Pesa confirms the payment.'
                : online
                  ? 'Inventory is deducted after the server confirms the sale.'
                  : 'Offline sales are stored on this device and synced with the server later.'}
            </small>
          </div>
        </section>
      </div>

      <ReceiptModal receipt={receipt} meta={meta} onClose={() => setReceipt(null)} />
    </>
  );
}

function Sales({ token, role, meta }) {
  const [filters, setFilters] = useState({ start: '', end: '', status: '' });
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  const { data: sales, error, busy: loading, refresh } = useLoad(
    () => api.sales(token, { ...filters, limit: 100 }),
    [token, filters.start, filters.end, filters.status],
  );

  async function openReceipt(sale) {
    try {
      const detail = await api.sale(token, sale.id);
      setSelected({
        number: detail.sale_number,
        at: detail.sale_time,
        items: detail.items,
        subtotal: detail.subtotal,
        discount: detail.discount,
        vat: detail.vat,
        total: detail.total,
        customer: detail.customer_name,
        cashier: detail.cashier,
        offline: detail.offline,
      });
    } catch (reason) {
      setNotice(reason.message);
    }
  }

  async function refund(sale) {
    if (!window.confirm(`Refund ${sale.sale_number} for ${money(sale.total)}? Stock will be restored.`)) return;
    setBusy(true);
    setNotice('');
    try {
      const reason = window.prompt('Reason for the refund (optional)') || '';
      const result = await api.refund(token, sale.id, reason);
      setNotice(`${result.sale_number} refunded. ${result.restored_items} line(s) returned to stock.`);
      await refresh();
    } catch (reason) {
      setNotice(reason.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <div><p className="eyebrow">TRANSACTION HISTORY</p><h2>Sales</h2></div>
        <button className="secondary-btn" onClick={refresh}>Refresh</button>
      </div>

      <div className="filter-row">
        <label>From<input type="date" value={filters.start} onChange={(event) => setFilters({ ...filters, start: event.target.value })} /></label>
        <label>To<input type="date" value={filters.end} onChange={(event) => setFilters({ ...filters, end: event.target.value })} /></label>
        <label>Status
          <select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
            <option value="">All</option>
            <option value="paid">Paid</option>
            <option value="refunded">Refunded</option>
          </select>
        </label>
      </div>

      {notice && <p className="notice" role="status">{notice}</p>}
      <LoadState busy={loading} error={error}>
        {sales && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr><th>Receipt</th><th>Date</th><th>Cashier</th><th>Status</th><th>Total</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {sales.map((sale) => (
                  <tr key={sale.id}>
                    <td>{sale.sale_number}{sale.offline && <span className="badge">offline</span>}</td>
                    <td>{formatDate(sale.sale_time, true)}</td>
                    <td>{sale.cashier}</td>
                    <td>
                      <span className={`badge ${sale.payment_status === 'refunded' ? 'danger' : 'ok'}`}>
                        {sale.payment_status}
                      </span>
                    </td>
                    <td>{money(sale.total)}</td>
                    <td className="table-actions">
                      <button className="link-btn" onClick={() => openReceipt(sale)}>Receipt</button>
                      {(role === 'owner' || role === 'manager') && sale.payment_status !== 'refunded' && (
                        <button className="link-btn danger" disabled={busy} onClick={() => refund(sale)}>Refund</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!sales.length && <div className="empty-state">No sales match these filters.</div>}
          </div>
        )}
      </LoadState>

      <ReceiptModal receipt={selected} meta={meta} onClose={() => setSelected(null)} />
    </section>
  );
}

function BarChart({ series }) {
  const max = Math.max(...series.map((point) => point.revenue), 1);
  const width = 640;
  const height = 180;
  const gap = 4;
  const barWidth = Math.max((width - gap * (series.length - 1)) / series.length, 1);
  const labelEvery = series.length > 16 ? 4 : series.length > 10 ? 2 : 1;

  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Revenue by interval">
      {series.map((point, index) => {
        const barHeight = Math.max(Math.round((point.revenue / max) * (height - 34)), point.revenue > 0 ? 3 : 0);
        const x = index * (barWidth + gap);
        return (
          <g key={`${point.label}-${index}`}>
            <rect x={x} y={height - 22 - barHeight} width={barWidth} height={barHeight} rx="2" className="chart-bar" />
            <title>{`${point.label}: ${money(point.revenue)} · ${point.transactions} sale(s)`}</title>
            {index % labelEvery === 0 && (
              <text x={x + barWidth / 2} y={height - 6} textAnchor="middle" className="chart-label">{point.label}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function Reports({ token, meta }) {
  const [period, setPeriod] = useState('daily');
  const [anchor, setAnchor] = useState(todayIso());
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');

  const { data, error, busy } = useLoad(() => api.report(token, period, anchor), [token, period, anchor]);

  async function exportCsv() {
    setExporting(true);
    setExportError('');
    try {
      const blob = await api.reportCsv(token, period, anchor);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${meta.store.toLowerCase().replace(/\s+/g, '-')}-${period}-${anchor}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setExportError(reason.message);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-heading">
          <div><p className="eyebrow">SALES ANALYTICS</p><h2>{data?.label || 'Reports'}</h2></div>
          <div className="segmented">
            {['daily', 'weekly', 'monthly'].map((option) => (
              <button
                key={option}
                className={period === option ? 'active' : ''}
                onClick={() => setPeriod(option)}
              >
                {option === 'daily' ? 'Today' : option === 'weekly' ? 'This week' : 'This month'}
              </button>
            ))}
          </div>
        </div>

        <div className="filter-row">
          <label>Anchor date
            <input type="date" value={anchor} onChange={(event) => setAnchor(event.target.value)} />
          </label>
          <div className="filter-actions">
            <button className="secondary-btn" onClick={exportCsv} disabled={exporting}>
              {exporting ? 'Exporting…' : 'Export CSV'}
            </button>
          </div>
        </div>

        {exportError && <p className="notice error" role="alert">{exportError}</p>}

        <LoadState busy={busy} error={error}>
          {data && (
            <>
              <div className="stats-grid four">
                <StatCard label="Revenue" value={compactMoney(data.totals.revenue)} detail={`${data.totals.transactions} sale(s)`} accent="gold" />
                <StatCard label="Average basket" value={compactMoney(data.totals.average_basket)} detail={`${data.totals.items_sold} items sold`} />
                <StatCard label="Gross profit" value={compactMoney(data.totals.gross_profit)} detail={`COGS ${compactMoney(data.totals.cogs)}`} />
                <StatCard label="Net after expenses" value={compactMoney(data.totals.net)} detail={`Expenses ${compactMoney(data.totals.expenses)}`} />
              </div>

              <p className="trend-line">
                {data.comparison.revenue_change_pct == null
                  ? 'No previous period to compare against.'
                  : data.comparison.revenue_change_pct >= 0
                    ? `Revenue is up ${data.comparison.revenue_change_pct}% versus the previous ${period === 'daily' ? 'day' : period === 'weekly' ? 'week' : 'month'}.`
                    : `Revenue is down ${Math.abs(data.comparison.revenue_change_pct)}% versus the previous ${period === 'daily' ? 'day' : period === 'weekly' ? 'week' : 'month'}.`}
                {data.totals.refunded_count > 0 && ` ${data.totals.refunded_count} refund(s) worth ${compactMoney(data.totals.refunded_amount)}.`}
                {` VAT included: ${compactMoney(data.totals.vat_included)}.`}
              </p>

              <div className="chart-wrap">
                <div className="chart-heading">
                  <p className="eyebrow">REVENUE BY {data.granularity === 'hour' ? 'HOUR' : 'DAY'}</p>
                  <span className="muted">{data.granularity === 'hour' ? '00:00 – 23:00' : 'Selected period'}</span>
                </div>
                <BarChart series={data.series} />
              </div>

              <div className="report-grid">
                <div className="panel inset">
                  <p className="eyebrow">TOP PRODUCTS</p>
                  {data.top_products.length ? (
                    <table>
                      <thead><tr><th>Product</th><th>Qty</th><th>Revenue</th></tr></thead>
                      <tbody>
                        {data.top_products.map((product) => (
                          <tr key={product.sku || product.name}>
                            <td>{product.name}</td><td>{product.quantity}</td><td>{money(product.revenue)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : <div className="empty-state">No products sold in this period.</div>}
                </div>

                <div className="panel inset">
                  <p className="eyebrow">PAYMENT MIX</p>
                  {data.payment_mix.length ? (
                    <ul className="meter-list">
                      {data.payment_mix.map((item) => (
                        <li key={item.method}>
                          <div className="meter-row"><strong>{item.method}</strong><span>{money(item.amount)}</span></div>
                          <div className="meter"><span style={{ width: `${Math.max((item.amount / Math.max(data.totals.revenue, 1)) * 100, 2)}%` }} /></div>
                          <small>{item.count} sale(s)</small>
                        </li>
                      ))}
                    </ul>
                  ) : <div className="empty-state">No payments in this period.</div>}
                </div>

                <div className="panel inset">
                  <p className="eyebrow">BY CASHIER</p>
                  {data.by_cashier.length ? (
                    <table>
                      <thead><tr><th>Cashier</th><th>Sales</th><th>Revenue</th></tr></thead>
                      <tbody>
                        {data.by_cashier.map((row) => (
                          <tr key={row.cashier}><td>{row.cashier}</td><td>{row.transactions}</td><td>{money(row.revenue)}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  ) : <div className="empty-state">No sales in this period.</div>}
                </div>

                <div className="panel inset">
                  <p className="eyebrow">RESTOCK ATTENTION</p>
                  {data.low_stock.length ? (
                    <ul className="plain-list">
                      {data.low_stock.map((product) => (
                        <li key={product.id}>
                          <span>{product.name}</span>
                          <strong>{product.stock_quantity} left</strong>
                        </li>
                      ))}
                    </ul>
                  ) : <div className="empty-state">Everything is above its reorder level.</div>}
                </div>
              </div>

              {data.expenses.length > 0 && (
                <div className="panel inset expense-inset">
                  <p className="eyebrow">TOP EXPENSES</p>
                  <ul className="plain-list">
                    {data.expenses.map((expense) => (
                      <li key={`${expense.description}-${expense.amount}`}>
                        <span>{expense.description} <small className="muted">{expense.category}</small></span>
                        <strong>{money(expense.amount)}</strong>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </LoadState>
      </section>
    </div>
  );
}

function Insights({ token, meta }) {
  const [period, setPeriod] = useState('daily');
  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState('');
  const [briefing, setBriefing] = useState(null);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.aiStatus(token)
      .then(setStatus)
      .catch((reason) => setStatusError(reason.message));
    api.aiBriefing(token, 'daily')
      .then(setBriefing)
      .catch(() => {});
  }, [token]);

  async function loadBriefing(nextPeriod) {
    setPeriod(nextPeriod);
    setAnswer(null);
    setError('');
    try {
      setBriefing(await api.aiBriefing(token, nextPeriod));
    } catch (reason) {
      setError(reason.message);
    }
  }

  async function ask(event) {
    event.preventDefault();
    if (!question.trim() || busy) return;
    setBusy(true);
    setError('');
    setAnswer(null);
    try {
      setAnswer(await api.aiAsk(token, question.trim(), period));
    } catch (reason) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  }

  const suggestions = [
    'What should I restock first and why?',
    'How can I raise the average basket size?',
    'Which products are driving profit this period?',
    'What does the trend suggest for tomorrow?',
  ];

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-heading">
          <div><p className="eyebrow">AI SALES ANALYST</p><h2>Ask about your numbers</h2></div>
          <span className={`badge ${status?.configured ? 'ok' : 'warning'}`}>
            {status?.configured ? `Live · ${status.model}` : 'Rules-based only'}
          </span>
        </div>

        <p className="muted">
          The analyst reads a computed snapshot of {meta.store}&rsquo;s sales and never sees raw customer
          or staff data. Every answer is grounded in the figures shown below it.
        </p>

        <div className="segmented">
          {['daily', 'weekly', 'monthly'].map((option) => (
            <button key={option} className={period === option ? 'active' : ''} onClick={() => loadBriefing(option)}>
              {option === 'daily' ? 'Today' : option === 'weekly' ? 'This week' : 'This month'}
            </button>
          ))}
        </div>

        {statusError && <p className="notice error" role="alert">{statusError}</p>}

        {!status?.configured && (
          <div className="notice warning setup-card">
            <strong>AI answers need one server-side key.</strong>
            <p>
              Set <code>ZAI_API_KEY</code> and <code>ZAI_API_BASE</code> in the API host&rsquo;s environment
              (never in the browser), then restart the API. Until then the rules-based briefing below still
              works and costs nothing.
            </p>
          </div>
        )}

        {briefing && (
          <div className="briefing">
            <p className="eyebrow">AUTO BRIEFING · {briefing.label}</p>
            <p>{briefing.briefing}</p>
            {briefing.top_products?.length > 0 && (
              <div className="chip-row">
                {briefing.top_products.map((product) => (
                  <span className="chip" key={product.name}>{product.name} · {product.quantity}</span>
                ))}
              </div>
            )}
          </div>
        )}

        <form className="ask-form" onSubmit={ask}>
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="e.g. What should I restock before the weekend?"
            maxLength={500}
          />
          <button className="primary-btn" disabled={busy || !question.trim()}>{busy ? 'Thinking…' : 'Ask analyst'}</button>
        </form>

        <div className="chip-row">
          {suggestions.map((suggestion) => (
            <button type="button" className="chip action" key={suggestion} onClick={() => setQuestion(suggestion)}>
              {suggestion}
            </button>
          ))}
        </div>

        {error && <p className="notice error" role="alert">{error}</p>}

        {answer && (
          <div className="answer">
            <p className="eyebrow">ANALYST · {answer.model}</p>
            <p className="answer-text">{answer.answer}</p>
            {answer.facts && (
              <div className="facts-grid">
                <div><span>Revenue</span><strong>{compactMoney(answer.facts.revenue)}</strong></div>
                <div><span>Sales</span><strong>{answer.facts.transactions}</strong></div>
                <div><span>Average basket</span><strong>{compactMoney(answer.facts.average_basket)}</strong></div>
                <div><span>Gross profit</span><strong>{compactMoney(answer.facts.gross_profit)}</strong></div>
                <div><span>Expenses</span><strong>{compactMoney(answer.facts.expenses)}</strong></div>
                <div><span>Net</span><strong>{compactMoney(answer.facts.net)}</strong></div>
              </div>
            )}
            <small className="muted">{answer.remaining} question(s) left on this account today.</small>
          </div>
        )}
      </section>
    </div>
  );
}

function Inventory({ token, role }) {
  const { data: products, error, busy, refresh } = useLoad(() => api.inventory(token), [token]);
  const [selectedId, setSelectedId] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(null);
  const canManage = role === 'owner' || role === 'manager';
  const [newProduct, setNewProduct] = useState({
    sku: '', name: '', category: '', buying_price: '', selling_price: '', stock_quantity: '0', reorder_level: '5',
  });

  async function receiveStock(event) {
    event.preventDefault();
    setSaving(true);
    setNotice('');
    try {
      await api.movement(token, {
        product_id: Number(selectedId),
        quantity: Number(quantity),
        type: 'receive',
        note: 'Stock received',
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
      await api.createProduct(token, {
        ...newProduct,
        unit: 'unit',
        buying_price: Number(newProduct.buying_price),
        selling_price: Number(newProduct.selling_price),
        stock_quantity: Number(newProduct.stock_quantity),
        reorder_level: Number(newProduct.reorder_level),
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

  async function saveProduct(event) {
    event.preventDefault();
    if (!editing) return;
    setSaving(true);
    setNotice('');
    try {
      await api.updateProduct(token, editing.id, {
        name: editing.name,
        category: editing.category,
        buying_price: Number(editing.buying_price),
        selling_price: Number(editing.selling_price),
        reorder_level: Number(editing.reorder_level),
        is_active: editing.is_active,
      });
      setNotice(`${editing.name} updated.`);
      setEditing(null);
      await refresh();
    } catch (reason) {
      setNotice(reason.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-heading">
          <div><p className="eyebrow">SHARED PRODUCT CATALOG</p><h2>Inventory</h2></div>
          <button className="secondary-btn" onClick={refresh}>Refresh</button>
        </div>
        <LoadState busy={busy} error={error}>
          {products && (
            <div className="table-scroll">
              <table>
                <thead><tr><th>Product</th><th>SKU</th><th>Category</th><th>Buying</th><th>Selling</th><th>On hand</th><th>Status</th>{canManage && <th />}</tr></thead>
                <tbody>
                  {products.map((product) => (
                    <tr key={product.id} className={product.is_active ? '' : 'inactive-row'}>
                      <td>{product.name}</td>
                      <td>{product.sku}</td>
                      <td>{product.category}</td>
                      <td>{money(product.buying_price)}</td>
                      <td>{money(product.selling_price)}</td>
                      <td>
                        <span className={product.stock_quantity <= product.reorder_level ? 'stock-low' : ''}>
                          {product.stock_quantity}
                        </span>
                      </td>
                      <td><span className={`badge ${product.is_active ? 'ok' : 'warning'}`}>{product.is_active ? 'active' : 'hidden'}</span></td>
                      {canManage && <td><button className="link-btn" onClick={() => setEditing({ ...product })}>Edit</button></td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </LoadState>
      </section>

      <div className="form-grid">
        <section className="panel">
          <p className="eyebrow">STOCK CONTROL</p><h2>Receive stock</h2>
          <form className="form-stack" onSubmit={receiveStock}>
            <label>Product
              <select required value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
                <option value="">Select a product</option>
                {(products || []).filter((product) => product.is_active).map((product) => (
                  <option value={product.id} key={product.id}>{product.name} · {product.stock_quantity} on hand</option>
                ))}
              </select>
            </label>
            <label>Quantity
              <input type="number" min="1" step="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} required />
            </label>
            <button className="primary-btn" disabled={saving || !selectedId}>{saving ? 'Saving…' : 'Record stock received'}</button>
          </form>
        </section>

        {canManage && (
          <section className="panel">
            <p className="eyebrow">CATALOG MANAGEMENT</p><h2>Add a product</h2>
            <form className="form-stack two-column-form" onSubmit={createProduct}>
              {[
                ['sku', 'SKU', 'text'], ['name', 'Product name', 'text'], ['category', 'Category', 'text'],
                ['buying_price', 'Buying price (KSh)', 'number'], ['selling_price', 'Selling price (KSh)', 'number'],
                ['stock_quantity', 'Opening stock', 'number'], ['reorder_level', 'Reorder level', 'number'],
              ].map(([field, label, type]) => (
                <label key={field}>{label}
                  <input
                    type={type}
                    min={type === 'number' ? '0' : undefined}
                    step={field === 'stock_quantity' || field === 'reorder_level' ? '1' : type === 'number' ? '0.01' : undefined}
                    required
                    value={newProduct[field]}
                    onChange={(event) => setNewProduct({ ...newProduct, [field]: event.target.value })}
                  />
                </label>
              ))}
              <button className="primary-btn" disabled={saving}>{saving ? 'Saving…' : 'Add product'}</button>
            </form>
          </section>
        )}
      </div>

      {notice && (
        <p className={`notice ${notice.includes('updated') || notice.includes('added') || notice.includes('received') ? 'success' : 'error'}`} role="status">
          {notice}
        </p>
      )}

      {editing && (
        <Modal title={editing.name} eyebrow="EDIT PRODUCT" onClose={() => setEditing(null)}>
          <form className="form-stack" onSubmit={saveProduct}>
            <div className="two-column-form">
              <label>Name<input value={editing.name} onChange={(event) => setEditing({ ...editing, name: event.target.value })} required /></label>
              <label>Category<input value={editing.category} onChange={(event) => setEditing({ ...editing, category: event.target.value })} /></label>
              <label>Buying price<input type="number" min="0" step="0.01" value={editing.buying_price} onChange={(event) => setEditing({ ...editing, buying_price: event.target.value })} /></label>
              <label>Selling price<input type="number" min="0" step="0.01" value={editing.selling_price} onChange={(event) => setEditing({ ...editing, selling_price: event.target.value })} /></label>
              <label>Reorder level<input type="number" min="0" step="1" value={editing.reorder_level} onChange={(event) => setEditing({ ...editing, reorder_level: event.target.value })} /></label>
              <label className="checkbox-label">
                <input type="checkbox" checked={editing.is_active} onChange={(event) => setEditing({ ...editing, is_active: event.target.checked })} />
                Visible in the catalog
              </label>
            </div>
            <button className="primary-btn" disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button>
          </form>
        </Modal>
      )}
    </div>
  );
}

function Expenses({ token }) {
  const { data: expenses, error, busy, refresh } = useLoad(() => api.expenses(token), [token]);
  const [form, setForm] = useState({ description: '', category: '', amount: '', payment_method: 'cash' });
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setNotice('');
    try {
      await api.createExpense(token, { ...form, amount: Number(form.amount) });
      setNotice('Expense recorded.');
      setForm({ description: '', category: '', amount: '', payment_method: 'cash' });
      await refresh();
    } catch (reason) {
      setNotice(reason.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="form-grid">
      <section className="panel">
        <p className="eyebrow">BUSINESS COSTS</p><h2>Record an expense</h2>
        <form className="form-stack" onSubmit={submit}>
          <label>Description<input value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} required /></label>
          <label>Category<input value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} /></label>
          <label>Amount (KSh)<input type="number" min="0.01" step="0.01" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} required /></label>
          <label>Payment method
            <select value={form.payment_method} onChange={(event) => setForm({ ...form, payment_method: event.target.value })}>
              <option value="cash">Cash</option><option value="mpesa">M-Pesa</option><option value="card">Card</option>
            </select>
          </label>
          <button className="primary-btn" disabled={saving}>{saving ? 'Saving…' : 'Save expense'}</button>
        </form>
        {notice && <p className="notice" role="status">{notice}</p>}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div><p className="eyebrow">RECENT COSTS</p><h2>Expenses</h2></div>
          <button className="secondary-btn" onClick={refresh}>Refresh</button>
        </div>
        <LoadState busy={busy} error={error}>
          {expenses?.length ? (
            <div className="table-scroll">
              <table>
                <thead><tr><th>Description</th><th>Category</th><th>Amount</th><th>Date</th></tr></thead>
                <tbody>
                  {expenses.map((expense) => (
                    <tr key={expense.id}>
                      <td>{expense.description}</td><td>{expense.category}</td>
                      <td>{money(expense.amount)}</td><td>{formatDate(expense.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="empty-state">No expenses recorded.</div>}
        </LoadState>
      </section>
    </div>
  );
}

function Users({ token, role }) {
  const { data: users, error, busy, refresh } = useLoad(() => api.users(token), [token]);
  const [form, setForm] = useState({ username: '', full_name: '', email: '', phone: '', password: '', role: 'cashier' });
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(null);

  async function submit(event) {
    event.preventDefault();
    setSaving(true);
    setNotice('');
    try {
      await api.createUser(token, form);
      setNotice('Staff account created.');
      setForm({ username: '', full_name: '', email: '', phone: '', password: '', role: 'cashier' });
      await refresh();
    } catch (reason) {
      setNotice(reason.message);
    } finally {
      setSaving(false);
    }
  }

  async function saveStaff(event) {
    event.preventDefault();
    if (!editing) return;
    setSaving(true);
    setNotice('');
    try {
      await api.updateUser(token, editing.id, {
        full_name: editing.full_name,
        phone: editing.phone || null,
        role: editing.role,
        is_active: editing.is_active,
        ...(editing.password ? { password: editing.password } : {}),
      });
      setNotice(`${editing.username} updated.`);
      setEditing(null);
      await refresh();
    } catch (reason) {
      setNotice(reason.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="form-grid">
      <section className="panel">
        <p className="eyebrow">STAFF ACCESS</p><h2>Create a staff account</h2>
        <form className="form-stack" onSubmit={submit}>
          <label>Full name<input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} required /></label>
          <label>Username<input autoComplete="off" value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} required /></label>
          <label>Email<input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required /></label>
          <label>Phone number (for SMS reset/login codes)<input type="tel" value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} placeholder="0712 345 678" /></label>
          <label>Temporary password<input type="password" minLength="6" autoComplete="new-password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required /></label>
          <label>Role
            <select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
              <option value="cashier">Cashier</option>
              <option value="stock">Stock</option>
              {role === 'owner' && <option value="manager">Manager</option>}
              {role === 'owner' && <option value="owner">Owner</option>}
            </select>
          </label>
          <button className="primary-btn" disabled={saving}>{saving ? 'Creating…' : 'Create account'}</button>
        </form>
        {notice && <p className="notice" role="status">{notice}</p>}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div><p className="eyebrow">TEAM</p><h2>Staff accounts</h2></div>
          <button className="secondary-btn" onClick={refresh}>Refresh</button>
        </div>
        <LoadState busy={busy} error={error}>
          {users?.length ? (
            <div className="table-scroll">
              <table>
                <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Status</th><th /></tr></thead>
                <tbody>
                  {users.map((staff) => (
                    <tr key={staff.id}>
                      <td>{staff.full_name}</td><td>{staff.username}</td><td>{staff.role}</td>
                      <td><span className={`badge ${staff.is_active ? 'ok' : 'warning'}`}>{staff.is_active ? 'active' : 'disabled'}</span></td>
                      <td><button className="link-btn" onClick={() => setEditing({ ...staff, password: '' })}>Manage</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="empty-state">No staff accounts found.</div>}
        </LoadState>
      </section>

      {editing && (
        <Modal title={editing.username} eyebrow="STAFF ACCOUNT" onClose={() => setEditing(null)}>
          <form className="form-stack" onSubmit={saveStaff}>
            <label>Full name<input value={editing.full_name} onChange={(event) => setEditing({ ...editing, full_name: event.target.value })} required /></label>
            <label>Phone number (for SMS reset/login codes)
              <input type="tel" value={editing.phone || ''} onChange={(event) => setEditing({ ...editing, phone: event.target.value })} placeholder="0712 345 678" />
            </label>
            <label>Role
              <select value={editing.role} onChange={(event) => setEditing({ ...editing, role: event.target.value })}>
                <option value="cashier">Cashier</option><option value="stock">Stock</option>
                <option value="manager">Manager</option><option value="owner">Owner</option>
              </select>
            </label>
            <label>Reset password (optional)
              <input type="password" minLength="6" autoComplete="new-password" value={editing.password} onChange={(event) => setEditing({ ...editing, password: event.target.value })} placeholder="Leave blank to keep current" />
            </label>
            <label className="checkbox-label">
              <input type="checkbox" checked={editing.is_active} onChange={(event) => setEditing({ ...editing, is_active: event.target.checked })} />
              Account can sign in
            </label>
            <button className="primary-btn" disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</button>
          </form>
        </Modal>
      )}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><App /></React.StrictMode>,
);
