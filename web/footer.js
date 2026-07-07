(function () {
  const FALLBACK_LINKS = [
    { id: "invest", label: "首页", title: "MyInvest 总览", url: "https://invest.okbbc.com/" },
    { id: "market", label: "市场", title: "A股市场评分", url: "https://market.okbbc.com/" },
    { id: "theme", label: "主线", title: "主题主线排名", url: "https://theme.okbbc.com/" },
    { id: "leader", label: "龙头", title: "龙头研究", url: "https://leader.okbbc.com/" },
    { id: "etf", label: "ETF", title: "ETF研究", url: "https://etf.okbbc.com/" },
    { id: "stock", label: "个股", title: "个股研究", url: "https://stock.okbbc.com/" },
    { id: "shadow", label: "影子", title: "影子观察", url: "https://shadow.okbbc.com/" },
    { id: "intraday", label: "看盘", title: "看盘", url: "https://intraday.okbbc.com/" },
    { id: "position", label: "操作", title: "仓位与执行", url: "https://position.okbbc.com/" },
    { id: "cycle", label: "周期", title: "周期", url: "https://cycle.okbbc.com/" },
    { id: "strategyindex", label: "策略", title: "策略", url: "https://strategyindex.okbbc.com/" },
    { id: "short", label: "短线", title: "短线", url: "https://short.okbbc.com/" },
    { id: "picking", label: "选股", title: "选股", url: "https://picking.okbbc.com/" },
    { id: "ten", label: "十倍", title: "十倍", url: "https://ten.okbbc.com/" },
  ];
  const CACHE_KEY = "myinvest:unified-footer:v15";
  const CACHE_TTL_MS = 10 * 60 * 1000;
  const DEFAULT_API_ORIGIN = "https://invest.okbbc.com";
  const CURRENT_SCRIPT = document.currentScript;

  function scriptApiUrl() {
    const script = CURRENT_SCRIPT;
    if (script?.dataset.api) return script.dataset.api;
    if (script?.src) {
      try {
        return `${new URL(script.src, window.location.href).origin}/api/footer`;
      } catch {
        return `${DEFAULT_API_ORIGIN}/api/footer`;
      }
    }
    return `${DEFAULT_API_ORIGIN}/api/footer`;
  }

  function mountTarget() {
    const script = CURRENT_SCRIPT;
    const selector = script?.dataset.target;
    if (selector) {
      const target = document.querySelector(selector);
      if (target) return target;
    }
    const dataTarget = document.querySelector("[data-myinvest-footer]");
    if (dataTarget) return dataTarget;
    const target = document.createElement("div");
    target.setAttribute("data-myinvest-footer", "");
    document.body.append(target);
    return target;
  }

  function ensureStyles() {
    if (document.getElementById("myinvest-unified-footer-style")) return;
    const style = document.createElement("style");
    style.id = "myinvest-unified-footer-style";
    style.textContent = `
      .mi-footer {
        border-top: 1px solid #d9dfd8;
        background: #f6f7f3;
        color: #17201b;
        font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", Arial, sans-serif;
        font-size: 13px;
      }
      .mi-footer__inner {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 14px;
        width: min(1280px, 100%);
        margin: 0 auto;
        padding: 12px 24px;
      }
      .mi-footer__meta,
      .mi-footer__links {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 8px 12px;
      }
      .mi-footer__brand {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        font-weight: 800;
        line-height: 1;
      }
      .mi-footer__logo-mark {
        width: 26px;
        height: 26px;
        flex: 0 0 auto;
      }
      .mi-footer__logo-shell {
        fill: #17201b;
      }
      .mi-footer__logo-bull {
        fill: #f6f7f3;
      }
      .mi-footer__logo-horn {
        fill: none;
        stroke: #f6f7f3;
        stroke-linecap: round;
        stroke-linejoin: round;
        stroke-width: 2.2;
      }
      .mi-footer__logo-eye {
        fill: #57b4bd;
      }
      .mi-footer__logo-muzzle {
        fill: none;
        stroke: #17201b;
        stroke-linecap: round;
        stroke-width: 1.2;
      }
      .mi-footer__logo-word {
        line-height: 1;
      }
      .mi-footer__pill {
        color: #637066;
      }
      .mi-footer__index {
        color: #166f7a;
        font-weight: 700;
        text-decoration: none;
      }
      .mi-footer__index:hover {
        text-decoration: underline;
      }
      .mi-footer__index--up {
        color: #b42318;
      }
      .mi-footer__index--down {
        color: #1d7f4d;
      }
      .mi-footer__link {
        color: #17201b;
        text-decoration: none;
      }
      .mi-footer__link:hover {
        text-decoration: underline;
      }
      @media (max-width: 720px) {
        .mi-footer__inner {
          align-items: flex-start;
          flex-direction: column;
          padding: 12px 16px;
        }
      }
    `;
    document.head.append(style);
  }

  function formatTime(value) {
    const date = value ? new Date(value) : new Date();
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(date);
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
      // Footer cache is best-effort.
    }
  }

  function clearNode(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function linkList(payload) {
    return Array.isArray(payload?.links) && payload.links.length ? payload.links : FALLBACK_LINKS;
  }

  function indexText(payload) {
    const index = payload?.market_index;
    if (!index?.available) return "上证指数 --";
    const change = index.change_display && index.change_pct_display
      ? ` ${index.change_display} (${index.change_pct_display})`
      : "";
    const suffix = index.as_of ? ` · ${index.as_of}` : "";
    return `${index.name || "上证指数"} ${index.display || "--"}${change}${suffix}`;
  }

  function render(target, payload) {
    ensureStyles();
    clearNode(target);

    const footer = document.createElement("footer");
    footer.className = "mi-footer";
    footer.setAttribute("role", "contentinfo");

    const inner = document.createElement("div");
    inner.className = "mi-footer__inner";

    const meta = document.createElement("div");
    meta.className = "mi-footer__meta";

    const brand = document.createElement("span");
    brand.className = "mi-footer__brand";

    const svgNamespace = "http://www.w3.org/2000/svg";
    const brandMark = document.createElementNS(svgNamespace, "svg");
    brandMark.setAttribute("class", "mi-footer__logo-mark");
    brandMark.setAttribute("aria-hidden", "true");
    brandMark.setAttribute("viewBox", "0 0 32 32");
    brandMark.setAttribute("focusable", "false");

    const shell = document.createElementNS(svgNamespace, "rect");
    shell.setAttribute("class", "mi-footer__logo-shell");
    shell.setAttribute("x", "3");
    shell.setAttribute("y", "3");
    shell.setAttribute("width", "26");
    shell.setAttribute("height", "26");
    shell.setAttribute("rx", "7");

    const horns = document.createElementNS(svgNamespace, "path");
    horns.setAttribute("class", "mi-footer__logo-horn");
    horns.setAttribute(
      "d",
      "M10.5 14.2C7.5 12.4 6.4 9.1 8.4 7.5C10.1 8.3 11.2 10.2 11.8 12.6M21.5 14.2C24.5 12.4 25.6 9.1 23.6 7.5C21.9 8.3 20.8 10.2 20.2 12.6",
    );

    const head = document.createElementNS(svgNamespace, "path");
    head.setAttribute("class", "mi-footer__logo-bull");
    head.setAttribute(
      "d",
      "M10.4 14.4C11.2 11.6 13.4 10.4 16 10.4C18.6 10.4 20.8 11.6 21.6 14.4L20.1 21.2C19.5 23.2 17.7 24.2 16 24.2C14.3 24.2 12.5 23.2 11.9 21.2Z",
    );

    const leftEye = document.createElementNS(svgNamespace, "circle");
    leftEye.setAttribute("class", "mi-footer__logo-eye");
    leftEye.setAttribute("cx", "14.2");
    leftEye.setAttribute("cy", "17.1");
    leftEye.setAttribute("r", "0.9");

    const rightEye = document.createElementNS(svgNamespace, "circle");
    rightEye.setAttribute("class", "mi-footer__logo-eye");
    rightEye.setAttribute("cx", "17.8");
    rightEye.setAttribute("cy", "17.1");
    rightEye.setAttribute("r", "0.9");

    const muzzle = document.createElementNS(svgNamespace, "path");
    muzzle.setAttribute("class", "mi-footer__logo-muzzle");
    muzzle.setAttribute("d", "M14.2 20.5C15.1 21.1 16.9 21.1 17.8 20.5");

    brandMark.append(shell, horns, head, leftEye, rightEye, muzzle);

    const brandWord = document.createElement("span");
    brandWord.className = "mi-footer__logo-word";
    brandWord.textContent = "MyInvest";

    brand.append(brandMark, brandWord);

    const time = document.createElement("span");
    time.className = "mi-footer__pill";
    time.setAttribute("data-mi-footer-time", "");
    time.textContent = formatTime(payload?.generated_at);

    const index = document.createElement(payload?.market_index?.link ? "a" : "span");
    index.className = "mi-footer__index";
    if (typeof payload?.market_index?.change === "number") {
      if (payload.market_index.change > 0) index.classList.add("mi-footer__index--up");
      if (payload.market_index.change < 0) index.classList.add("mi-footer__index--down");
    }
    if (payload?.market_index?.link) {
      index.href = payload.market_index.link;
      index.target = "_blank";
      index.rel = "noopener noreferrer";
    }
    index.textContent = indexText(payload);

    meta.append(brand, time, index);

    const nav = document.createElement("nav");
    nav.className = "mi-footer__links";
    nav.setAttribute("aria-label", "MyInvest 系统链接");

    for (const item of linkList(payload)) {
      const link = document.createElement("a");
      link.className = "mi-footer__link";
      link.href = item.url;
      link.textContent = item.label;
      link.title = item.title || item.label;
      nav.append(link);
    }

    inner.append(meta, nav);
    footer.append(inner);
    target.append(footer);

    window.clearInterval(target.__myInvestFooterTimer);
    target.__myInvestFooterTimer = window.setInterval(() => {
      const timeNode = target.querySelector("[data-mi-footer-time]");
      if (timeNode) timeNode.textContent = formatTime();
    }, 1000);
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
      // Keep fallback or cached footer visible when the API is unavailable.
    }
  }

  function start() {
    const target = mountTarget();
    const cached = readCache();
    render(target, cached || { generated_at: new Date().toISOString(), links: FALLBACK_LINKS });
    hydrate(target, scriptApiUrl());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
