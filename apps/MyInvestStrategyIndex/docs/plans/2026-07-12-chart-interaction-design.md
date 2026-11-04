# Chart Interaction Design

The comparison page becomes chart-first. Time controls occupy the first full row and ETF selection occupies the second, so a large observation universe no longer pushes the chart below unrelated controls. Y-axis and navigation controls move into a compact toolbar above the primary chart.

The primary chart provides two explicit pointer modes. Pan mode preserves the current drag-to-pan behavior. Range mode lets the user drag across the plot to select and zoom into a date interval. A live crosshair follows the pointer in either idle mode and displays the nearest date plus the current value for every visible series. The tooltip is bounded and scrollable so large ETF selections remain usable.

The feature is implemented in the shared comparison renderer so all strategy comparison pages receive the same behavior. Automated tests verify the required controls and interaction code, followed by browser checks for layout, crosshair visibility, and range zoom.
