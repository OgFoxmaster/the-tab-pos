// Single place that knows how to talk to the FastAPI backend.
export const API_BASE_URL = (
  window.__TABPOS_API__ ||
  import.meta.env.VITE_API_BASE_URL ||
  'http://localhost:8000'
).replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(message, status = 0, data = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export async function request(path, token, options = {}) {
  const { method = 'GET', body, headers, signal } = options;
  let response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      signal,
      headers: {
        ...(body ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    if (error?.name === 'AbortError') throw error;
    throw new ApiError(
      `Could not reach the POS server at ${API_BASE_URL}. Sales can continue offline and sync later.`,
      0,
    );
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      data?.detail || data?.message || 'The request could not be completed.',
      response.status,
      data,
    );
  }
  return data;
}

function query(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, value);
  });
  const text = search.toString();
  return text ? `?${text}` : '';
}

export const api = {
  login: (username, password, login_code, login_challenge) =>
    request('/login', null, { method: 'POST', body: { username, password, login_code, login_challenge } }),
  me: (token) => request('/me', token),
  meta: () => request('/meta'),

  products: (token, { includeInactive = false } = {}) =>
    request(`/products${query({ include_inactive: includeInactive || undefined })}`, token),
  createProduct: (token, payload) =>
    request('/products', token, { method: 'POST', body: payload }),
  updateProduct: (token, id, payload) =>
    request(`/products/${id}`, token, { method: 'PATCH', body: payload }),

  inventory: (token) => request('/inventory?include_inactive=true', token),
  movement: (token, payload) =>
    request('/inventory/movement', token, { method: 'POST', body: payload }),

  sales: (token, params = {}) => request(`/sales${query(params)}`, token),
  sale: (token, id) => request(`/sales/${id}`, token),
  createSale: (token, payload) =>
    request('/sales', token, { method: 'POST', body: payload }),
  refund: (token, id, reason) =>
    request(`/sales/${id}/refund`, token, { method: 'POST', body: { reason } }),

  expenses: (token) => request('/expenses', token),
  createExpense: (token, payload) =>
    request('/expenses', token, { method: 'POST', body: payload }),

  users: (token) => request('/users', token),
  createUser: (token, payload) =>
    request('/users', token, { method: 'POST', body: payload }),
  updateUser: (token, id, payload) =>
    request(`/users/${id}`, token, { method: 'PATCH', body: payload }),

  dashboard: (token) => request('/dashboard/summary', token),

  report: (token, period, anchor) =>
    request(`/reports/summary${query({ period, anchor })}`, token),
  reportCsv: async (token, period, anchor) => {
    const response = await fetch(
      `${API_BASE_URL}/reports/export.csv${query({ period, anchor })}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    if (!response.ok) throw new ApiError('Could not export the report.', response.status);
    return response.blob();
  },

  aiStatus: (token) => request('/ai/status', token),
  aiBriefing: (token, period, anchor) =>
    request(`/ai/briefing${query({ period, anchor })}`, token),
  aiAsk: (token, question, period) =>
    request('/ai/insights', token, { method: 'POST', body: { question, period } }),

  setupStatus: () => request('/auth/setup-status'),
  registerOwner: (payload) =>
    request('/auth/register-owner', null, { method: 'POST', body: payload }),
  company: (token) => request('/company', token),
  branches: (token) => request('/branches', token),
  createBranch: (token, payload) => request('/branches', token, { method: 'POST', body: payload }),
  forgotPassword: (email, phone) =>
    request('/auth/forgot-password', null, { method: 'POST', body: { email, phone: phone || undefined } }),
  resetPassword: (token, password) =>
    request('/auth/reset-password', null, { method: 'POST', body: { token, password } }),

  mpesaPayment: (token, payload) =>
    request('/payments/mpesa', token, { method: 'POST', body: payload }),
  paymentStatus: (token, reference) => request(`/payments/${reference}`, token),
  verifyPayment: (token, reference) =>
    request(`/payments/${reference}/verify`, token, { method: 'POST' }),
  simulatePayment: (token, reference, outcome) =>
    request(`/mpesa/simulate/${reference}?outcome=${outcome}`, token, { method: 'POST' }),
};
