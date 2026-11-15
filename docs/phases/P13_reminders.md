# P13 — Reminders & Local Notifications

**Goal:** The user is notified on time about warranty expiry, return deadlines, last installments and budgets — without server push.
**Depends on:** P12 · **Week:** 11
**Read first:** spec §12

## Scope

### Backend
1. `app/reminders/scheduler.py`: recompute reminders for a target whenever its deadline changes (warranty set/changed, return window set/changed, plan created/changed, budget threshold crossed). Rules: warranty −30 d and −7 d at 10:00; return −3 d and −1 d at 10:00; INSTALLMENT_END on the 1st of the last due month at 10:00; budgets immediately. Europe/Istanbul.
2. Idempotent upsert (unique on user, type, target, fire_at); delete reminders of deleted/returned targets.
3. `GET /reminders/upcoming?days=60` (not dismissed, fire_at ≥ now − 1 day); `POST /reminders/{id}/dismiss`.

### Mobile
4. `flutter_local_notifications` + `timezone`; request POST_NOTIFICATIONS (Android 13+) with an explanation screen; exact alarms if permitted, else inexact.
5. Sync on app start/resume and after any mutation that can change deadlines: cancel all scheduled ReceiptBox notifications → schedule from `/reminders/upcoming` (notification id = stable hash of reminder id).
6. Notification texts (Turkish): "AirPods'un garanti süresinin bitmesine 30 gün kaldı.", "Trendyol'dan aldığın ayakkabının iade süresi yarın bitiyor.", "Market bütçenin %80'ine ulaştın.", "MediaMarkt taksitlerinin sonuncusu bu ay." Tapping opens the related screen (deep link).
7. Settings: per-type notification toggles (stored locally).

## Out of scope

FCM/server push, e-mail reminders.

## Acceptance criteria

- [ ] Changing a warranty end date reschedules exactly the right reminders (backend tests).
- [ ] Reminders for a returned product disappear.
- [ ] On a device, a reminder set 2 minutes ahead (debug helper) fires and deep-links correctly.
- [ ] No duplicate notifications after multiple app resumes.

## Tests

`test_reminder_rules.py`, `test_reminder_idempotency.py`, Dart unit test for id hashing and scheduling diff.

## Manual check for the owner

Use the debug "fire in 2 minutes" button for each type and tap the notifications.
