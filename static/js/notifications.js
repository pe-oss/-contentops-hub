document.addEventListener("DOMContentLoaded", () => {
  const notifWrapper = document.getElementById("notificationDropdownWrapper");
  const notifBtn = document.getElementById("notificationDropdownBtn");
  const notifPanel = document.getElementById("notificationDropdownPanel");
  const notifBadge = document.getElementById("topbarNotificationBadge");
  const notifMarkAllBtn = document.getElementById("notifMarkAllBtn");
  const notifTabAll = document.getElementById("notifTabAll");
  const notifTabUnread = document.getElementById("notifTabUnread");
  const notifItemsList = document.getElementById("notifItemsList");
  const notifStateMsg = document.getElementById("notifStateMessage");
  const notifFooter = document.getElementById("notifPanelFooter");
  const notifLoadMoreBtn = document.getElementById("notifLoadMoreBtn");

  if (!notifWrapper || !notifBtn || !notifPanel) return;

  const endpoint = notifWrapper.dataset.endpoint;
  const readAllEndpoint = notifWrapper.dataset.readAllEndpoint;

  function getCsrfToken() {
    return (
      notifWrapper.dataset.csrf ||
      document.querySelector("[name=csrfmiddlewaretoken]")?.value ||
      (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] ||
      ""
    );
  }

  let isOpen = false;
  let currentTab = "all";
  let currentPage = 1;
  let hasNext = false;
  let isLoading = false;
  let hasLoaded = false;

  function updateBadge(count) {
    if (!notifBadge) return;
    const unreadCount = parseInt(count, 10) || 0;
    if (unreadCount <= 0) {
      notifBadge.style.display = "none";
      notifBadge.textContent = "0";
    } else {
      notifBadge.style.display = "inline-block";
      notifBadge.textContent = unreadCount > 99 ? "99+" : unreadCount;
    }
  }

  function openDropdown() {
    isOpen = true;
    notifPanel.style.display = "flex";
    notifBtn.setAttribute("aria-expanded", "true");
    if (!hasLoaded) {
      fetchNotifications(1, false);
    }
  }

  function closeDropdown() {
    if (!isOpen) return;
    isOpen = false;
    notifPanel.style.display = "none";
    notifBtn.setAttribute("aria-expanded", "false");
  }

  notifBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (isOpen) {
      closeDropdown();
    } else {
      openDropdown();
    }
  });

  document.addEventListener("click", (e) => {
    if (isOpen && !notifWrapper.contains(e.target)) {
      closeDropdown();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && isOpen) {
      closeDropdown();
      notifBtn.focus();
    }
  });

  function setTab(tab) {
    if (currentTab === tab && hasLoaded) return;
    currentTab = tab;
    if (tab === "all") {
      notifTabAll?.classList.add("active");
      notifTabAll?.setAttribute("aria-selected", "true");
      notifTabUnread?.classList.remove("active");
      notifTabUnread?.setAttribute("aria-selected", "false");
    } else {
      notifTabUnread?.classList.add("active");
      notifTabUnread?.setAttribute("aria-selected", "true");
      notifTabAll?.classList.remove("active");
      notifTabAll?.setAttribute("aria-selected", "false");
    }
    currentPage = 1;
    fetchNotifications(1, false);
  }

  if (notifTabAll) notifTabAll.addEventListener("click", () => setTab("all"));
  if (notifTabUnread) notifTabUnread.addEventListener("click", () => setTab("unread"));

  function getEventIcon(eventType) {
    switch (eventType) {
      case "ASSIGNMENT": return "👤";
      case "REVIEW_REQUEST": return "📝";
      case "CHANGES_REQUESTED": return "✏️";
      case "BLOCKED": return "⛔";
      case "UNBLOCKED": return "✅";
      default: return "🔔";
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function createNotificationItem(notif) {
    const item = document.createElement("div");
    item.className = `notif-item ${notif.is_read ? "" : "unread"}`;
    item.setAttribute("role", "article");
    item.setAttribute("tabindex", "0");
    item.dataset.id = notif.id;
    item.dataset.readUrl = notif.read_url;
    item.dataset.targetUrl = notif.target_url || "";
    item.dataset.isRead = notif.is_read ? "true" : "false";

    const icon = getEventIcon(notif.event_type);
    const iconClass = `notif-icon-box icon-${notif.event_type || "DEFAULT"}`;

    item.innerHTML = `
      <div class="${iconClass}" aria-hidden="true">${icon}</div>
      <div class="notif-item-body">
        <div class="notif-item-title">${escapeHtml(notif.title)}</div>
        ${notif.message ? `<div class="notif-item-message">${escapeHtml(notif.message)}</div>` : ""}
        <div class="notif-item-time">${escapeHtml(notif.created_at_display || "")}</div>
      </div>
      ${notif.is_read ? "" : `<div class="notif-unread-dot" aria-label="Chưa đọc"></div>`}
    `;

    function handleItemClick(e) {
      e.preventDefault();
      const readUrl = item.dataset.readUrl;
      const targetUrl = item.dataset.targetUrl;
      const isCurrentlyRead = item.dataset.isRead === "true";

      if (!isCurrentlyRead && readUrl) {
        fetch(readUrl, {
          method: "POST",
          headers: {
            "X-CSRFToken": getCsrfToken(),
            "X-Requested-With": "XMLHttpRequest",
          },
        })
          .then((res) => res.json())
          .then((data) => {
            item.classList.remove("unread");
            item.dataset.isRead = "true";
            const dot = item.querySelector(".notif-unread-dot");
            if (dot) dot.remove();
            if (data && typeof data.unread_count !== "undefined") {
              updateBadge(data.unread_count);
            }
            if (targetUrl) window.location.href = targetUrl;
          })
          .catch(() => {
            if (targetUrl) window.location.href = targetUrl;
          });
      } else if (targetUrl) {
        window.location.href = targetUrl;
      }
    }

    item.addEventListener("click", handleItemClick);
    item.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") handleItemClick(e);
    });

    return item;
  }
  function fetchNotifications(page = 1, append = false) {
    if (isLoading) return;
    isLoading = true;

    const sep = endpoint.includes("?") ? "&" : "?";
    const statusParam = currentTab === "unread" ? "&status=unread" : "";
    const url = `${endpoint}${sep}format=json&page=${page}${statusParam}`;

    if (!append) {
      notifStateMsg.style.display = "block";
      notifStateMsg.innerHTML = "Đang tải thông báo...";
      notifItemsList.innerHTML = "";
      notifFooter.style.display = "none";
    } else {
      notifLoadMoreBtn.textContent = "Đang tải...";
      notifLoadMoreBtn.disabled = true;
    }

    fetch(url, {
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
      },
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP error ${res.status}`);
        return res.json();
      })
      .then((data) => {
        isLoading = false;
        hasLoaded = true;
        currentPage = data.page || page;
        hasNext = Boolean(data.has_next);

        updateBadge(data.unread_count);

        if (!append) notifItemsList.innerHTML = "";

        const notifications = data.notifications || [];
        if (notifications.length === 0 && !append) {
          notifStateMsg.style.display = "block";
          notifStateMsg.innerHTML =
            currentTab === "unread"
              ? "✨ Không có thông báo chưa đọc nào."
              : "✨ Bạn không có thông báo nào.";
        } else {
          notifStateMsg.style.display = "none";
          notifications.forEach((n) => {
            notifItemsList.appendChild(createNotificationItem(n));
          });
        }

        if (hasNext) {
          notifFooter.style.display = "flex";
          notifLoadMoreBtn.style.display = "inline-block";
          notifLoadMoreBtn.textContent = "Tải thêm";
          notifLoadMoreBtn.disabled = false;
        } else {
          notifLoadMoreBtn.style.display = "none";
          if (!append && notifications.length === 0) {
            notifFooter.style.display = "none";
          } else {
            notifFooter.style.display = "flex";
          }
        }
      })
      .catch(() => {
        isLoading = false;
        if (!append) {
          notifStateMsg.style.display = "block";
          notifStateMsg.innerHTML = `⚠️ Không thể tải thông báo.<br><button type="button" class="notif-retry-btn" id="notifRetryBtn">Thử lại</button>`;
          const retryBtn = document.getElementById("notifRetryBtn");
          if (retryBtn) retryBtn.addEventListener("click", () => fetchNotifications(page, append));
        } else {
          notifLoadMoreBtn.textContent = "Thử lại";
          notifLoadMoreBtn.disabled = false;
        }
      });
  }

  if (notifLoadMoreBtn) {
    notifLoadMoreBtn.addEventListener("click", () => {
      if (hasNext && !isLoading) fetchNotifications(currentPage + 1, true);
    });
  }

  if (notifMarkAllBtn && readAllEndpoint) {
    notifMarkAllBtn.addEventListener("click", (e) => {
      e.preventDefault();
      fetch(readAllEndpoint, {
        method: "POST",
        headers: {
          "X-CSRFToken": getCsrfToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
      })
        .then((res) => res.json())
        .then(() => {
          updateBadge(0);
          if (currentTab === "unread") {
            notifItemsList.innerHTML = "";
            notifStateMsg.style.display = "block";
            notifStateMsg.innerHTML = "✨ Không có thông báo chưa đọc nào.";
            notifFooter.style.display = "none";
          } else {
            notifItemsList.querySelectorAll(".notif-item.unread").forEach((el) => {
              el.classList.remove("unread");
              el.dataset.isRead = "true";
              const dot = el.querySelector(".notif-unread-dot");
              if (dot) dot.remove();
            });
          }
        })
        .catch((err) => {
          console.error("Mark all read failed", err);
        });
    });
  }
});
