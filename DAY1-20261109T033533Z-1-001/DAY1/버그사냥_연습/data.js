// 가상의 예시 상품 — 가상의 서귀포 감귤 농가 「돌담귤방」. 가격 · 제철은 강의용 예시 값입니다.
(function (root) {
  const PRODUCTS = [
    { id: 'gyul-5', name: '노지감귤 5kg', price: 29000, season: { from: 11, to: 2 }, tags: ['기본'] },
    { id: 'gyul-10', name: '노지감귤 10kg', price: 49000, season: { from: 11, to: 2 }, tags: ['대용량'] },
    { id: 'hallabong-3', name: '한라봉 3kg', price: 39000, season: { from: 1, to: 3 }, tags: ['선물'] },
    { id: 'cheonhye-3', name: '천혜향 3kg', price: 42000, season: { from: 2, to: 4 }, tags: ['선물'] },
    { id: 'mix-2', name: '만감류 맛보기 세트 2kg', price: 30000, season: { from: 2, to: 3 }, tags: ['선물', '세트'] },
    { id: 'syrup', name: '감귤청 500g', price: 15000, season: { from: 1, to: 12 }, tags: ['가공품', '선물'] },
    { id: 'chips', name: '귤 말랭이 3봉', price: 12000, season: { from: 1, to: 12 }, tags: ['가공품'] },
  ];
  if (typeof module !== 'undefined' && module.exports) module.exports = PRODUCTS;
  else root.PRODUCTS = PRODUCTS;
})(typeof window !== 'undefined' ? window : this);
