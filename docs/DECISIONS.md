# Decisions Log

Format: `D-NNN · date · decision · reason`. Only the owner moves items from "Open" or "Proposed" to "Accepted".

## Accepted

| ID | Date | Decision | Reason |
|---|---|---|---|
| D-001 | 2026-11-15 | Single-semester project, scope per spec §3 | Instructor approval for one semester |
| D-002 | 2026-11-15 | Android only (Flutter); no iOS | Owner uses Windows; reduces effort |
| D-003 | 2026-11-15 | Free LLM tier (Gemini) behind `AIProvider`; mandatory on-device masking | No budget; privacy mitigation |
| D-004 | 2026-11-15 | Target users 18+, general adult population; UI Turkish; no parental consent flow | Owner decision |
| D-005 | 2026-11-15 | Home order: spending (top) → needs attention → due this month (bottom); budgets on spending view | Owner decision |
| D-006 | 2026-11-15 | Manual cash purchases and basic (full/partial) refunds in MVP; installment cancellation manual; TRY only | Cheap, prevents data gaps |
| D-007 | 2026-11-15 | Observations (evidence) vs transactions (canonical) model; reversible merges | Needed for 1:1 and 1:N matching and research logging |
| D-008 | 2026-11-15 | No Redis/Celery/FCM/offline sync/RAG in MVP | Single-semester scope |
| D-009 | 2026-11-15 | Money stored as BIGINT minor units | Avoid float errors |
| D-010 | 2026-11-15 | Claude Code writes the code; owner reviews/tests each phase | Owner decision |
| D-011 | 2026-11-15 | All md docs in English | Owner decision |

## Open (need owner input)

| ID | Question | Needed by |
|---|---|---|
| O-001 | Which 2–3 banks to support? Owner will provide masked screenshots (list view, an installment row, detail view). | P08 |
| O-002 | Final visual design (colors, typography, key screens) — design track with Figma/Claude. | P03 (placeholder tokens until then) |
| O-003 | Sample receipts incl. an e-Archive invoice with QR and a POS slip with installments. | P05 |

## Proposed / not approved

_(Claude Code: write feature ideas here instead of implementing them.)_
