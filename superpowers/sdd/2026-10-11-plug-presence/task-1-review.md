# Task 1 review
Spec: PASS. Quality: approved.
1. 30 commits carried in brief order (17 + 13); `git cherry` vs branch-3 shows all 17 step-2 commits present (-) and none of f939ff8/490c7cb; vs branch 4 the 6 "+" ... 7 partials show as "+" (patch differs, expected), 6 whole commits as "-". None of 045160f 443b181 8764711 6805b0b b0a86f9 0b46958 carried.
2. `git diff --name-only presence/4-arrive-depart HEAD` = the two presence files only. Those files diffed against c7d4cf1 equal exactly the reverse of a2855bb..490c7cb (the telemetry-limit fill): line multiset identical.
3. Whole commits: message and author identical to source (-C). Partials: bodies equal source plus the "Carried without..." paragraph before the Opus 5.5 trailer; subjects replaced for fada5b4, 05437b7, 32d798a only.
Findings: Minor: partial commits have a new author date (commit -F), harmless.
