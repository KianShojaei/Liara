'use strict';

const express = require('express');
const { productsHandler, checkoutHandler, slowHandler, healthHandler } = require('./handlers/shop');

const PORT = Number(process.env.PORT || 3000);
const app = express();
app.use(express.json());

app.use((req, res, next) => {
  const started = process.hrtime.bigint();
  res.on('finish', () => {
    const ms = Number(process.hrtime.bigint() - started) / 1e6;
    console.log(`${req.method} ${req.path} ${res.statusCode} ${ms.toFixed(1)}ms`);
  });
  next();
});

app.get('/', (_req, res) => res.json({ name: 'shop-demo', version: '1.0.0', fault: process.env.FAULT_MODE || 'none' }));
app.get('/health', healthHandler);
app.get('/api/products', productsHandler);
app.post('/api/checkout', checkoutHandler);
app.get('/slow', slowHandler);

app.use((err, _req, res, _next) => {
  console.error(err.stack || String(err));
  res.status(500).json({ error: 'internal error' });
});

app.listen(PORT, () => console.log(`shop-demo listening on ${PORT} (FAULT_MODE=${process.env.FAULT_MODE || 'none'})`));
