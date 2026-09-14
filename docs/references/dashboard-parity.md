# Dashboard parity reference

Inspected read-only on 2026-09-14 from `Trade-Dividend-Bot`, branch `feature/dashboard-refresh-discovery-summary`, file `src/dividend_bot/enterprise_watchlist_ui.py`.

Reusable conventions:

- Page ink `#10213b`; supporting text `#53627a`/`#64748b`; white raised surfaces; `#f4f7fc` table headers; `#dbe4f0` borders.
- Status pills: ready `#e9f9f0/#087443`, watch `#fff7df/#8a4b08`, blocked `#fff0f0/#b42318`, unavailable `#f1f5f9/#7a8798`.
- Purple `#5b21b6` is used for emphasis/focus; focus ring is 2px with offset.
- Cards use 12–13px radii and subtle navy shadows.
- Executive tables use uppercase compact headers, tabular numeric alignment, honest “Not reported”/pending values, and horizontal overflow where needed.
- Evidence drill-down controls expose authoritative details without changing calculations.
- Summary grids collapse from four columns to two near 900px and one near 520px.
- Screen-reader-only context is retained for unavailable authoritative evidence.

The live `ai-cio-platform` dashboards could not be inspected because Remote Desktop Commander was unavailable. Final deployment verification must compare the rendered option dashboard against the authoritative live Swing and Dividend views and validate the AI CIO View-link convention.
