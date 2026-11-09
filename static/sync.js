"use strict";

// 第6週の共有・同期。第7週ではカテゴリ変更も監視します。
const statusText = document.getElementById("sync-status");
const reloadButton = document.getElementById("sync-reload");
const initialSnapshot = document.getElementById("initial-snapshot");

if (statusText && reloadButton && initialSnapshot) {
  const initialData = JSON.parse(initialSnapshot.textContent);

  function makeSignature(data) {
    return JSON.stringify({
      today: data.today,
      foods: data.foods.map(food => [
        food.id, food.name, food.quantity, food.unit,
        food.expiration_date, food.category
      ]),
      shopping_items: data.shopping_items.map(item => [
        item.id, item.name, item.quantity, item.unit
      ])
    });
  }

  const initialSignature = makeSignature(initialData);
  let isEditing = false;
  let isChecking = false;

  function showStatus(message, showReload = false) {
    statusText.textContent = message;
    reloadButton.hidden = !showReload;
  }

  document.addEventListener("input", event => {
    if (event.target.closest("form")) isEditing = true;
  });
  document.addEventListener("change", event => {
    if (event.target.closest("form")) isEditing = true;
  });
  reloadButton.addEventListener("click", () => window.location.reload());

  async function checkForUpdates() {
    if (isChecking || document.hidden) return;
    isChecking = true;
    try {
      const response = await fetch("/api/state", {cache: "no-store"});
      if (!response.ok) throw new Error("同期情報を取得できません");
      const latestData = await response.json();
      const latestSignature = makeSignature(latestData);
      if (latestSignature !== initialSignature) {
        const active = document.activeElement;
        const inputFocused = active && active.matches("input, select, textarea");
        if (isEditing || inputFocused) {
          showStatus("他の端末で更新されました。最新情報を確認してください。", true);
        } else {
          window.location.reload();
        }
      } else {
        showStatus("最新の状態に同期されています");
      }
    } catch (error) {
      console.error(error);
      showStatus("同期できません。通信状態を確認してください。", true);
    } finally {
      isChecking = false;
    }
  }

  setInterval(checkForUpdates, 15000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) checkForUpdates();
  });
  checkForUpdates();
}
