# US ETF Strategy Observer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Build a grouped 23-ETF observation page centered on CAGR, drawdown, volatility, and Calmar, with a daily dynamic equal-weight comparison.

**Architecture:** Reuse the Yahoo adjusted-price data source and generic comparison UI. Configure four ETF groups and one synthetic equal-weight series; the browser recomputes that series from currently selected real ETFs. Correct the inflation page by separating its monthly strategy curve from a daily dynamic equal-weight benchmark.

**Tech Stack:** Python, pandas, yfinance, vanilla HTML/CSS/JavaScript, pytest.

---

1. Add grouped ETF definitions, payload getter, and cached adjusted-history tests.
2. Add page/API routes, home card, grouped controls, and Calmar-first labels.
3. Make dynamic equal-weight selection exclude every synthetic series and recompute from checked real ETFs.
4. Replace the inflation equal-weight server curve with the daily dynamic comparison.
5. Run all tests, refresh real data, and verify both pages in the browser.
