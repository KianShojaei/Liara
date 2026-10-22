'use strict';

const PRODUCTS = [
  { id: 1, name: 'کیبورد مکانیکی', price: 2_450_000 },
  { id: 2, name: 'ماوس بی‌سیم', price: 890_000 },
  { id: 3, name: 'هدست گیمینگ', price: 1_990_000 },
];

// "Response cache" that never evicts: the memory leak used by the demo (FAULT_MODE=leak).
const responseCache = [];

function faultMode() {
  return (process.env.FAULT_MODE || 'none').toLowerCase();
}

function productsHandler(req, res) {
  if (faultMode() === 'leak') {
    // Every request keeps ~1MB alive forever.
    responseCache.push({ at: Date.now(), body: Buffer.alloc(1024 * 1024, 1), query: req.query });
    if (responseCache.length % 50 === 0) console.warn(`[warn] cache size growing: entries=${responseCache.length}`);
  }
  res.json({ products: PRODUCTS, cached: responseCache.length });
}

function checkoutHandler(req, res) {
  const items = Array.isArray(req.body.items) ? req.body.items : [];
  const total = computeTotal(items, faultMode() === 'error');
  res.json({ total, currency: 'IRT' });
}

function computeTotal(items, broken) {
  return items.reduce((sum, item) => {
    const product = PRODUCTS.find((p) => p.id === item.id);
    // FAULT_MODE=error: a product lookup that can be undefined is dereferenced without a guard.
    const price = broken ? product.price : (product ? product.price : 0);
    return sum + price * (item.qty || 1);
  }, 0);
}

function slowHandler(_req, res) {
  const burn = faultMode() === 'slow' ? 1500 : 5;
  const end = Date.now() + burn;
  while (Date.now() < end) {
    // busy loop: CPU saturation for the demo
  }
  res.json({ took_ms: burn });
}

function healthHandler(_req, res) {
  const mem = process.memoryUsage();
  res.json({ status: 'ok', rss_mb: Math.round(mem.rss / 1024 / 1024), heap_mb: Math.round(mem.heapUsed / 1024 / 1024), cache_entries: responseCache.length });
}

module.exports = { productsHandler, checkoutHandler, slowHandler, healthHandler, computeTotal };
