(function () {
  const FALLBACK_LINKS = [
    { id: "invest", label: "首页", title: "MyInvest 总览", url: "https://invest.okbbc.com/" },
    { id: "market", label: "市场", title: "A股市场评分", url: "https://market.okbbc.com/" },
    { id: "theme", label: "主线", title: "主题主线排名", url: "https://theme.okbbc.com/" },
    { id: "cycle", label: "周期", title: "周期", url: "https://cycle.okbbc.com/" },
    { id: "shadow", label: "影子", title: "影子观察", url: "https://shadow.okbbc.com/" },
    { id: "leader", label: "龙头", title: "龙头研究", url: "https://leader.okbbc.com/" },
    { id: "ten", label: "十倍", title: "十倍", url: "https://ten.okbbc.com/" },
    { id: "etf", label: "ETF", title: "ETF研究", url: "https://etf.okbbc.com/" },
    { id: "picking", label: "选股", title: "选股", url: "https://picking.okbbc.com/" },
    { id: "stock", label: "个股", title: "个股研究", url: "https://stock.okbbc.com/" },
    { id: "short", label: "短线", title: "短线", url: "https://short.okbbc.com/" },
    { id: "position", label: "操作", title: "仓位与执行", url: "https://position.okbbc.com/" },
  ];
  const CACHE_KEY = "myinvest:unified-header:v6";
  const CACHE_TTL_MS = 10 * 60 * 1000;
  const DEFAULT_API_ORIGIN = "https://invest.okbbc.com";
  const CURRENT_SCRIPT = document.currentScript;

  function scriptApiUrl() {
    const script = CURRENT_SCRIPT;
    if (script?.dataset.api) return script.dataset.api;
    if (script?.src) {
      try {
        return `${new URL(script.src, window.location.href).origin}/api/header`;
      } catch {
        return `${DEFAULT_API_ORIGIN}/api/header`;
      }
    }
    return `${DEFAULT_API_ORIGIN}/api/header`;
  }

  function mountTarget() {
    const script = CURRENT_SCRIPT;
    const selector = script?.dataset.target;
    if (selector) {
      const target = document.querySelector(selector);
      if (target) return target;
    }
    const dataTarget = document.querySelector("[data-myinvest-header]");
    if (dataTarget) return dataTarget;
    const target = document.createElement("div");
    target.setAttribute("data-myinvest-header", "");
    document.body.prepend(target);
    return target;
  }

  function ensureStyles() {
    if (document.getElementById("myinvest-unified-header-style")) return;
    const style = document.createElement("style");
    style.id = "myinvest-unified-header-style";
    style.textContent = `
      .mi-header {
        position: sticky;
        top: 0;
        z-index: 1000;
        border-bottom: 1px solid #d9dfd8;
        background: #f6f7f3;
        color: #17201b;
        font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", Arial, sans-serif;
        font-size: 14px;
      }
      .mi-header__inner {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        width: min(1280px, 100%);
        margin: 0 auto;
        padding: 10px 24px;
      }
      .mi-header__brand {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        color: #17201b;
        min-height: 34px;
        line-height: 1;
        text-decoration: none;
        white-space: nowrap;
      }
      .mi-header__logo-mark {
        width: 32px;
        height: 32px;
        flex: 0 0 auto;
      }
      .mi-header__logo-shell {
        fill: #17201b;
      }
      .mi-header__logo-bull {
        fill: #f6f7f3;
      }
      .mi-header__logo-horn {
        fill: none;
        stroke: #f6f7f3;
        stroke-linecap: round;
        stroke-linejoin: round;
        stroke-width: 2.2;
      }
      .mi-header__logo-eye {
        fill: #57b4bd;
      }
      .mi-header__logo-muzzle {
        fill: none;
        stroke: #17201b;
        stroke-linecap: round;
        stroke-width: 1.2;
      }
      .mi-header__logo-word {
        font-size: 16px;
        font-weight: 800;
        line-height: 1;
      }
      .mi-header__brand:hover .mi-header__logo-mark {
        color: #166f7a;
      }
      .mi-header__brand:hover .mi-header__logo-shell {
        fill: #166f7a;
      }
      .mi-header__nav {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: flex-end;
        gap: 4px;
      }
      .mi-header__link {
        border-radius: 6px;
        color: #36443a;
        line-height: 1;
        min-height: 30px;
        padding: 8px 10px;
        text-decoration: none;
        white-space: nowrap;
      }
      .mi-header__link:hover,
      .mi-header__link--active {
        background: #e9eee7;
        color: #166f7a;
      }
      @media (max-width: 720px) {
        .mi-header__inner {
          align-items: flex-start;
          flex-direction: column;
          padding: 10px 16px;
        }
        .mi-header__nav {
          justify-content: flex-start;
        }
      }
    `;
    document.head.append(style);
  }

  function readCache() {
    try {
      const raw = localStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      const cached = JSON.parse(raw);
      if (!cached.stored_at || Date.now() - cached.stored_at > CACHE_TTL_MS) {
        localStorage.removeItem(CACHE_KEY);
        return null;
      }
      return cached.payload;
    } catch {
      return null;
    }
  }

  function writeCache(payload) {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify({ stored_at: Date.now(), payload }));
    } catch {
      // Header cache is best-effort.
    }
  }

  function clearNode(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function linkList(payload) {
    return Array.isArray(payload?.links) && payload.links.length ? payload.links : FALLBACK_LINKS;
  }

  function brandInfo(payload) {
    return payload?.brand?.label && payload?.brand?.url
      ? payload.brand
      : { label: "MyInvest", url: "https://invest.okbbc.com/" };
  }

  function isActiveLink(url) {
    try {
      const linkUrl = new URL(url, window.location.href);
      return linkUrl.hostname === window.location.hostname;
    } catch {
      return false;
    }
  }

  function render(target, payload) {
    ensureStyles();
    clearNode(target);

    const header = document.createElement("header");
    header.className = "mi-header";
    header.setAttribute("role", "banner");

    const inner = document.createElement("div");
    inner.className = "mi-header__inner";

    const brand = brandInfo(payload);
    const brandLink = document.createElement("a");
    brandLink.className = "mi-header__brand";
    brandLink.href = brand.url;
    brandLink.setAttribute("aria-label", brand.label);

    const svgNamespace = "http://www.w3.org/2000/svg";
    const brandMark = document.createElementNS(svgNamespace, "svg");
    brandMark.setAttribute("class", "mi-header__logo-mark");
    brandMark.setAttribute("aria-hidden", "true");
    brandMark.setAttribute("viewBox", "0 0 32 32");
    brandMark.setAttribute("focusable", "false");

    const shell = document.createElementNS(svgNamespace, "rect");
    shell.setAttribute("class", "mi-header__logo-shell");
    shell.setAttribute("x", "3");
    shell.setAttribute("y", "3");
    shell.setAttribute("width", "26");
    shell.setAttribute("height", "26");
    shell.setAttribute("rx", "7");

    const horns = document.createElementNS(svgNamespace, "path");
    horns.setAttribute("class", "mi-header__logo-horn");
    horns.setAttribute(
      "d",
      "M10.5 14.2C7.5 12.4 6.4 9.1 8.4 7.5C10.1 8.3 11.2 10.2 11.8 12.6M21.5 14.2C24.5 12.4 25.6 9.1 23.6 7.5C21.9 8.3 20.8 10.2 20.2 12.6",
    );

    const head = document.createElementNS(svgNamespace, "path");
    head.setAttribute("class", "mi-header__logo-bull");
    head.setAttribute(
      "d",
      "M10.4 14.4C11.2 11.6 13.4 10.4 16 10.4C18.6 10.4 20.8 11.6 21.6 14.4L20.1 21.2C19.5 23.2 17.7 24.2 16 24.2C14.3 24.2 12.5 23.2 11.9 21.2Z",
    );

    const leftEye = document.createElementNS(svgNamespace, "circle");
    leftEye.setAttribute("class", "mi-header__logo-eye");
    leftEye.setAttribute("cx", "14.2");
    leftEye.setAttribute("cy", "17.1");
    leftEye.setAttribute("r", "0.9");

    const rightEye = document.createElementNS(svgNamespace, "circle");
    rightEye.setAttribute("class", "mi-header__logo-eye");
    rightEye.setAttribute("cx", "17.8");
    rightEye.setAttribute("cy", "17.1");
    rightEye.setAttribute("r", "0.9");

    const muzzle = document.createElementNS(svgNamespace, "path");
    muzzle.setAttribute("class", "mi-header__logo-muzzle");
    muzzle.setAttribute("d", "M14.2 20.5C15.1 21.1 16.9 21.1 17.8 20.5");

    brandMark.append(shell, horns, head, leftEye, rightEye, muzzle);

    const brandWord = document.createElement("span");
    brandWord.className = "mi-header__logo-word";
    brandWord.textContent = brand.label;

    brandLink.append(brandMark, brandWord);

    const nav = document.createElement("nav");
    nav.className = "mi-header__nav";
    nav.setAttribute("aria-label", "MyInvest 系统导航");

    for (const item of linkList(payload)) {
      const link = document.createElement("a");
      link.className = "mi-header__link";
      link.href = item.url;
      link.textContent = item.label;
      link.title = item.title || item.label;
      if (isActiveLink(item.url)) {
        link.classList.add("mi-header__link--active");
        link.setAttribute("aria-current", "page");
      }
      nav.append(link);
    }

    inner.append(brandLink, nav);
    header.append(inner);
    target.append(header);
  }

  async function hydrate(target, apiUrl) {
    try {
      const response = await fetch(`${apiUrl}${apiUrl.includes("?") ? "&" : "?"}t=${Date.now()}`, {
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      writeCache(payload);
      render(target, payload);
    } catch {
      // Keep fallback or cached header visible when the API is unavailable.
    }
  }

  function start() {
    const target = mountTarget();
    const cached = readCache();
    render(target, cached || { brand: { label: "MyInvest", url: "https://invest.okbbc.com/" }, links: FALLBACK_LINKS });
    hydrate(target, scriptApiUrl());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
