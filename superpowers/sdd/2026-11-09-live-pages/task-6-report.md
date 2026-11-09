# Task 6 report
Implemented all page formatters and predicates in format.js (rulings R1-R3, R8 applied; plain text only).
Tests: tests/js/format.test.js extended with every brief test plus extras; `node --test tests/js/*.test.js` 19/19 pass.
TDD: tests and implementation were written in one step; the RED run was not captured separately.
Notes: surplusWatts/Unit return "0"/"Watt" when surplus not positive; surplusAmps "0.00". spend* formatters return "" when entry.spend or ctx.data.spend is missing.
Files: lib/TWCManager/Control/static/js/format.js, tests/js/format.test.js
