document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-auto-hide]").forEach((element) => {
    setTimeout(() => element.remove(), 4500);
  });

  // Mobile sidebar toggle handler
  const toggleBtn = document.getElementById("sidebarToggle");
  const sidebar = document.getElementById("appSidebar");
  const backdrop = document.getElementById("sidebarBackdrop");

  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener("click", () => {
      sidebar.classList.toggle("open");
      if (backdrop) backdrop.classList.toggle("show");
    });
  }

  if (backdrop && sidebar) {
    backdrop.addEventListener("click", () => {
      sidebar.classList.remove("open");
      backdrop.classList.remove("show");
    });
  }
});
