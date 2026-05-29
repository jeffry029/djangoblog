/**
 * 收藏本站按钮 + 站点统计展示组件
 * 显示总浏览量、收藏人数，点击触发浏览器收藏并计数
 */
const STORAGE_KEY = 'djangoblog-bookmarked';

function getCsrfToken() {
  const name = 'csrftoken';
  const cookies = document.cookie.split(';');
  for (let cookie of cookies) {
    cookie = cookie.trim();
    if (cookie.startsWith(name + '=')) {
      return decodeURIComponent(cookie.substring(name.length + 1));
    }
  }
  return '';
}

export default () => ({
  totalViews: 0,
  bookmarkCount: 0,
  isBookmarked: false,
  loading: true,

  init() {
    this.isBookmarked = localStorage.getItem(STORAGE_KEY) === 'true';
    this.fetchStats();
  },

  async fetchStats() {
    try {
      const resp = await fetch('/_internal/bookmark/stats/');
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.success) {
        this.totalViews = data.total_views;
        this.bookmarkCount = data.bookmark_count;
      }
    } catch {
      // silently fail — stats are cosmetic
    } finally {
      this.loading = false;
    }
  },

  async addBookmark() {
    if (this.isBookmarked) return;

    // Trigger browser bookmark
    this.triggerBrowserBookmark();

    // POST to backend
    try {
      const resp = await fetch('/_internal/bookmark/add/', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrfToken() },
      });
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.success) {
        this.bookmarkCount = data.bookmark_count;
        this.isBookmarked = true;
        localStorage.setItem(STORAGE_KEY, 'true');
      }
    } catch {
      // Mark as bookmarked locally even if API fails
      this.isBookmarked = true;
      localStorage.setItem(STORAGE_KEY, 'true');
    }
  },

  triggerBrowserBookmark() {
    const title = document.title;
    const url = window.location.href;

    // IE / old Edge
    if (window.external && window.external.addFavorite) {
      window.external.addFavorite(url, title);
      return;
    }

    // Show keyboard shortcut hint via a brief toast
    this.showToast(
      navigator.userAgent.includes('Mac')
        ? '按 Cmd+D 收藏本站'
        : '按 Ctrl+D 收藏本站'
    );
  },

  showToast(msg) {
    // Create a temporary toast element
    const toast = document.createElement('div');
    toast.textContent = msg;
    toast.className = 'bookmark-toast';
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  },
});