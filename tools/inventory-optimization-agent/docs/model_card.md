# Forecast and recommendation card

- **Data:** Locally generated synthetic weekly demand for eight SKUs over 104 weeks.
- **Backtest:** Last eight observations held out; four-week mean and seasonal-naive reference, with MAE.
- **Recommendation:** Mean demand over last eight weeks, sample standard deviation, lead-time square-root buffer, policy factor, and on-hand plus incoming stock.
- **Action boundary:** Output is only a draft. No supplier, PO, or external action capability exists.
- **Limits:** No stockout censoring, promotions, new/discontinued SKU lifecycle, MOQ, supplier calendars, unit costs, uncertainty intervals, or real-world impact evidence.
