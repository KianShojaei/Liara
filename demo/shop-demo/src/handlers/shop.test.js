'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { computeTotal } = require('./shop');

test('computes totals for known products', () => {
  assert.strictEqual(computeTotal([{ id: 1, qty: 2 }], false), 4_900_000);
});

test('ignores unknown products when not broken', () => {
  assert.strictEqual(computeTotal([{ id: 99 }], false), 0);
});
