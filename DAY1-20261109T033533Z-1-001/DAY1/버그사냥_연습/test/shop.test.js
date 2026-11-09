// node --test 로 실행 — 이 파일은 고치지 않습니다(테스트 = 사람이 정한 기준).
const test = require('node:test');
const assert = require('node:assert');
const { formatPrice, inSeason, pickGifts, byTag } = require('../shop.js');
const PRODUCTS = require('../data.js');

test('가격: 29000 → 29,000원', () => assert.strictEqual(formatPrice(29000), '29,000원'));
test('가격: 0 → 0원', () => assert.strictEqual(formatPrice(0), '0원'));
test('가격: 1234567 → 1,234,567원 (큰 금액)', () => assert.strictEqual(formatPrice(1234567), '1,234,567원'));

test('제철: 한라봉(1~3월)은 2월에 제철', () => assert.strictEqual(inSeason({ season: { from: 1, to: 3 } }, 2), true));
test('제철: 노지감귤(11월~2월)은 1월에도 제철 (해를 넘김)', () => assert.strictEqual(inSeason({ season: { from: 11, to: 2 } }, 1), true));

test('선물: 예산 30000 이면 정확히 30000원 상품도 포함', () => {
  const names = pickGifts(PRODUCTS, 30000).map(p => p.name);
  assert.ok(names.includes('만감류 맛보기 세트 2kg'), '결과: ' + names.join(', '));
});
test('선물: 비싼 순 최대 3개', () => {
  const prices = pickGifts(PRODUCTS, 100000).map(p => p.price);
  assert.deepStrictEqual(prices, [49000, 42000, 39000]);
});
test('태그: 선물 태그 상품 4개', () => assert.strictEqual(byTag(PRODUCTS, '선물').length, 4));
