// 버그사냥_연습 — 1일차 6교시용. 일부러 버그 3개를 심어 둔 계산 함수 모음입니다.
// 브라우저에서는 window.Shop, node 에서는 require('./shop.js') 로 씁니다.
// ⚠ 이 파일은 연습용 — 버그 위치는 강사용 교안에만 있습니다.
(function (root) {
  // 가격을 '29,000원' 처럼 쉼표와 '원'을 붙여 보여 준다
  function formatPrice(won) {
    const n = Math.round(Number(won) || 0);
    return String(n).replace(/(\d)(?=(\d{3})+$)/, '$1,') + '원';
  }

  // 이번 달(1~12)이 상품의 제철인지 — season = { from: 달, to: 달 }
  function inSeason(product, month) {
    const { from, to } = product.season;
    return month >= from && month <= to;
  }

  // 예산 이하의 상품을 비싼 순으로 최대 3개
  function pickGifts(products, budget) {
    return products
      .filter(p => p.price < budget)
      .sort((a, b) => b.price - a.price)
      .slice(0, 3);
  }

  // 태그로 고르기 (예: '선물')
  function byTag(products, tag) {
    return products.filter(p => (p.tags || []).includes(tag));
  }

  const api = { formatPrice, inSeason, pickGifts, byTag };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Shop = api;
})(typeof window !== 'undefined' ? window : this);
