import test from 'node:test';
import assert from 'node:assert/strict';
import { formatAmount } from './amount.mjs';

test('préserve le wei au-delà de la précision JavaScript', () => {
  assert.equal(formatAmount('1000000000000000001', 18), '1,000000000000000001');
  assert.equal(formatAmount('400000000000000001', 18), '0,400000000000000001');
});
test('préserve uint256 max, zéro et les décimales inconnues', () => {
  const max = (2n ** 256n - 1n).toString();
  assert.equal(formatAmount(max, 0), max);
  assert.equal(formatAmount('0', 18), '0');
  assert.equal(formatAmount('1', 6), '0,000001');
  assert.equal(formatAmount('42', null), '42 unités brutes (décimales inconnues)');
  assert.throws(() => formatAmount('1e18', 18));
});
