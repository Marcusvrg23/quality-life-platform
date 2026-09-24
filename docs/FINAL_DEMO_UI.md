# Final demo UI

The Django demo uses a shared authenticated shell, an eight-item read-only exercise library, and a nine-region SVG quality map. Scores, bands, completion dates and pillar identities remain backend-persisted values. There are no model, schema, seed, scoring or authentication changes.

## Exercise provenance

Source: `MEMBROS INFERIORES E SUPERIORES- QUALITYLIFE AP.pdf`, supplied by the project owner (28 pages). Page references are one-based. Extracted images are saved as WebP under `static/quality_life/images/exercises/`; the original PDF and prototype assets are untouched.

| Exercise | Instructions | Image |
| --- | --- | --- |
| Autoabraço | 2 | 2 |
| Abertura do peito | 2 | 3 |
| Alongamento do pescoço | 6 | 7 |
| Braços e punhos | 7 | 8 |
| Alongamento lateral | 12 | 13 |
| Passo largo e braços elevados | 22 | 23 |
| Panturrilha com apoio | Visual demonstration only, 25; professional guidance, 28 | 25, third illustration |
| Dedos e punhos na cadeira | Caption in illustration, 26 | 26, first illustrated position |

The initial position for series 1 comes from page 1. Safety text summarizes pages 1 and 28. The calf entry explicitly states that the source has no detailed steps, duration or repetitions. No timer or persistent exercise completion is implemented. Category filters and the guided sequence operate only in the current page. Without JavaScript, native expandable instructions remain available.

## Verification

Use the existing PostgreSQL-backed Django suite, including `tests.test_assessment_browser`, `tests.test_assessment_result`, `tests.test_exercises` and `tests.test_app_shell`. CI installs pinned agent-browser 0.36.0 and connects it to the browser's local CDP port for checkpoints on the actual Django live test server. QA data is isolated in the test database and does not change the demo seed.

Browser artifacts cover 390×844, 430×932, 1366×768 and 1440×900. The notebook does not have PostgreSQL; local DB-free tests and login preview are supplemental, while GitHub Actions runs the full PostgreSQL and end-to-end gates. No SQLite fallback or database configuration change is used.

No merge or deployment is part of this candidate.
