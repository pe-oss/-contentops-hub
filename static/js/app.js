document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-auto-hide]").forEach((element) => {
    setTimeout(() => element.remove(), 4500);
  });
});