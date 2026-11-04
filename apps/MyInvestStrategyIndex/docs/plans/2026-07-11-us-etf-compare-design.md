# US ETF Compare Design

The new `/us-etf-compare` research page mirrors the existing comparison experience while keeping the first version deliberately simple. It displays RSP, IWY, MOAT, SPMO, PFF, and VNQ as individual adjusted-price series and adds one synthetic portfolio that is rebalanced to equal weights across all six available ETFs. Each target weight is 1/6 (16.67%).

US prices come from Yahoo Finance through `yfinance` and are cached in the existing runtime cache directory. Adjusted Close is used so distributions and splits are represented in the comparison. A refresh request bypasses the cache. Partial source failures are reported in the existing error panel, and the equal-weight portfolio is calculated when at least two component histories are available.

The page reuses the current charts, drawdown view, scatter plot, date controls, metric ranking, and refresh interaction. It gets a dedicated API route and a strategy-research card on the home page. Existing comparison pages remain unchanged.
