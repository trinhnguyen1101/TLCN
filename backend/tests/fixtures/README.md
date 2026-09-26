`dashboard.json` was captured by executing the original
`frontend/src/services/mockDashboardData.ts` with JavaScript before removing it.
It is a regression fixture, never a runtime data source. It verifies every value,
date, province code (including leading zeros), field name and array ordering
against the previous dashboard, including JavaScript rounding behavior.
