"use strict";

// 第7週：ページ内の食材名検索とカテゴリ絞り込み
const searchInput = document.getElementById("food-search");
const categorySelect = document.getElementById("food-category-filter");
const foodCards = [...document.querySelectorAll(".food-item")];
const resultCount = document.getElementById("food-result-count");
const noMatch = document.getElementById("food-no-match");

function normalizeText(value) {
  return value.normalize("NFKC").toLocaleLowerCase("ja-JP").trim();
}

function filterFoods() {
  const keyword = normalizeText(searchInput.value);
  const category = categorySelect.value;
  let visibleCount = 0;

  for (const card of foodCards) {
    const nameMatches = normalizeText(card.dataset.name).includes(keyword);
    const categoryMatches = !category || card.dataset.category === category;
    const visible = nameMatches && categoryMatches;
    card.hidden = !visible;
    if (visible) visibleCount++;
  }

  resultCount.textContent = `${visibleCount}件 / 全${foodCards.length}件`;
  noMatch.hidden = foodCards.length === 0 || visibleCount > 0;
}

if (searchInput && categorySelect && resultCount && noMatch) {
  searchInput.addEventListener("input", filterFoods);
  categorySelect.addEventListener("change", filterFoods);
  filterFoods();
}
