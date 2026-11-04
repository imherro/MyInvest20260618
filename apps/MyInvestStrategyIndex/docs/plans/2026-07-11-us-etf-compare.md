# US ETF Compare Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Add a six-fund US ETF comparison page with one 16.67%-per-fund equal-weight portfolio.

**Architecture:** Extend the generic comparison data pipeline with a US ETF source backed by adjusted Yahoo Finance history, then configure a dedicated instrument set and synthetic equal-weight series. Reuse the existing comparison page renderer with route-specific labels and metadata.

**Tech Stack:** Python stdlib HTTP server, pandas, yfinance, vanilla HTML/CSS/JavaScript, pytest.

---

### Task 1: Data model and source

**Files:**
- Modify: `myinvest_strategy_index/value_compare.py`
- Modify: `requirements.txt`
- Test: `tests/test_value_compare.py`

1. Add a failing payload test for the six symbols and equal-weight series.
2. Add `US_ETF_COMPARE_INSTRUMENTS` and `get_us_etf_compare_payload`.
3. Route `us_etf` instruments to a Yahoo Finance adjusted-price loader.
4. Run the focused data tests.

### Task 2: Page, API, and navigation

**Files:**
- Modify: `myinvest_strategy_index/webapp.py`
- Test: `tests/test_webapp.py`

1. Add failing tests for the home card, page route metadata, and API route.
2. Add `/us-etf-compare` and `/api/us-etf-compare/history.json`.
3. Add the home card and page renderer using the existing chart experience.
4. Run the focused web tests.

### Task 3: Verification

**Files:**
- Modify: `README.md`

1. Document the new page and data source.
2. Run the full test suite.
3. Restart the local server, refresh the browser, and verify the page visually and through its live API.
