// Offline support for the till.
//
// Products are cached so the catalog still renders without a network connection.
// Cash sales completed while offline are written to an IndexedDB queue and replayed
// to POST /sales with a client_reference, which makes the server idempotent.
import { api } from './api.js';

const DB_NAME = 'tabpos-offline';
const DB_VERSION = 1;
const memory = { kv: new Map(), queue: new Map() };
let dbPromise = null;

function idbAvailable() {
  try {
    return typeof indexedDB !== 'undefined' && indexedDB !== null;
  } catch {
    return false;
  }
}

function openDb() {
  if (!idbAvailable()) return Promise.resolve(null);
  if (dbPromise) return dbPromise;

  dbPromise = new Promise((resolve, reject) => {
    const open = indexedDB.open(DB_NAME, DB_VERSION);
    open.onupgradeneeded = () => {
      const db = open.result;
      if (!db.objectStoreNames.contains('kv')) db.createObjectStore('kv', { keyPath: 'key' });
      if (!db.objectStoreNames.contains('queue')) {
        db.createObjectStore('queue', { keyPath: 'client_reference' });
      }
    };
    open.onsuccess = () => resolve(open.result);
    open.onerror = () => reject(open.error);
  }).catch(() => null);

  return dbPromise;
}

function transaction(db, storeName, mode, run) {
  return new Promise((resolve, reject) => {
    const store = db.transaction(storeName, mode).objectStore(storeName);
    const request = run(store);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function kvGet(key) {
  const db = await openDb();
  if (!db) return memory.kv.get(key) ?? null;
  const entry = await transaction(db, 'kv', 'readonly', (store) => store.get(key));
  return entry ? entry.value : null;
}

export async function kvSet(key, value) {
  const db = await openDb();
  if (!db) {
    memory.kv.set(key, value);
    return;
  }
  await new Promise((resolve, reject) => {
    const request = db.transaction('kv', 'readwrite').objectStore('kv').put({ key, value });
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

export async function cacheProducts(products) {
  await kvSet('products', { products, cachedAt: new Date().toISOString() });
}

export async function cachedProducts() {
  const entry = await kvGet('products');
  return entry?.products ?? null;
}

export async function applyLocalStock(items) {
  const entry = await kvGet('products');
  if (!entry?.products) return null;
  const sold = new Map(items.map((item) => [item.product_id, item.quantity]));
  const products = entry.products.map((product) =>
    sold.has(product.id)
      ? { ...product, stock_quantity: Math.max(0, product.stock_quantity - sold.get(product.id)) }
      : product,
  );
  await kvSet('products', { ...entry, products, cachedAt: new Date().toISOString() });
  return products;
}

export async function queueSale(sale) {
  const record = {
    ...sale,
    queued_at: new Date().toISOString(),
    attempts: 0,
    last_error: null,
  };
  const db = await openDb();
  if (!db) {
    memory.queue.set(record.client_reference, record);
    return record;
  }
  await new Promise((resolve, reject) => {
    const request = db.transaction('queue', 'readwrite').objectStore('queue').put(record);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
  return record;
}

export async function pendingSales() {
  const db = await openDb();
  if (!db) return [...memory.queue.values()];
  return new Promise((resolve, reject) => {
    const request = db.transaction('queue', 'readonly').objectStore('queue').getAll();
    request.onsuccess = () => resolve(request.result || []);
    request.onerror = () => reject(request.error);
  });
}

export async function pendingCount() {
  return (await pendingSales()).length;
}

export async function removeQueued(clientReference) {
  const db = await openDb();
  if (!db) {
    memory.queue.delete(clientReference);
    return;
  }
  await new Promise((resolve, reject) => {
    const request = db.transaction('queue', 'readwrite').objectStore('queue').delete(clientReference);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

export async function markAttempt(clientReference, error) {
  const queued = await pendingSales();
  const record = queued.find((sale) => sale.client_reference === clientReference);
  if (!record) return;
  const db = await openDb();
  const next = {
    ...record,
    attempts: (record.attempts || 0) + 1,
    last_error: String(error || 'Unknown error').slice(0, 300),
  };
  if (!db) {
    memory.queue.set(clientReference, next);
    return;
  }
  await new Promise((resolve, reject) => {
    const request = db.transaction('queue', 'readwrite').objectStore('queue').put(next);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

export function toSalePayload(sale) {
  return {
    payment_method: 'cash',
    items: sale.items.map((item) => ({
      product_id: item.product_id,
      quantity: item.quantity,
    })),
    discount: sale.discount || 0,
    customer_name: sale.customer_name || undefined,
    client_reference: sale.client_reference,
    sold_at: sale.sold_at,
  };
}

export async function syncPending(token) {
  const queued = await pendingSales();
  const result = { synced: 0, failed: 0, remaining: queued.length, errors: [] };

  for (const sale of queued) {
    try {
      await api.createSale(token, toSalePayload(sale));
      await removeQueued(sale.client_reference);
      result.synced += 1;
    } catch (error) {
      await markAttempt(sale.client_reference, error.message);
      // 4xx means the server rejected this sale for a reason a retry will not fix.
      if (error.status >= 400 && error.status < 500) {
        result.failed += 1;
        result.errors.push(`${sale.receipt_number || sale.client_reference}: ${error.message}`);
        continue;
      }
      break; // Network or server problem: keep the rest queued and retry later.
    }
  }

  result.remaining = await pendingCount();
  return result;
}
