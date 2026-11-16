# Design Track

Runs in parallel with P00–P04. Output: approved screens + design tokens that P03 and later phases implement.

## Workflow

1. Owner and Claude define direction (mood, references, colors) in chat.
2. Key screens are drafted (Claude design canvas or Figma). Owner edits in Figma if preferred.
3. With the Figma connector enabled, Claude reads frames (`get_design_context`, `get_screenshot`, `get_variable_defs`) and turns tokens into `mobile/lib/core/theme/`.
4. Each approved screen is linked below; implementation phases reference it.

## Screens to design (priority order)

| # | Screen | Used in phase | Status | Link |
|---|---|---|---|---|
| 1 | Home (spending → attention → due this month) | P11 | 🟨 Draft v1 | [Figma](https://www.figma.com/design/dXpZpN53pLMmkYylQwmK1H) · frame "01 · Ana Sayfa" |
| 2 | Receipt review (fields + confidence badges + items) | P07 | 🟨 Draft v1 | [Figma](https://www.figma.com/design/dXpZpN53pLMmkYylQwmK1H) · frame "02 · Fiş Kontrol" |
| 3 | Bank import review (rows + match badges) | P08–P10 | ⬜ | |
| 4 | Match suggestion sheet | P09 | ⬜ | |
| 5 | Product detail (warranty, return, documents) | P12 | ⬜ | |
| 6 | Assistant chat (suggested questions, action buttons) | P14 | ⬜ | |
| 7 | (+) action sheet, bottom navigation | P03 | ✅ Bottom nav built from the Figma component (node 2:22). 🟨 The (+) sheet is a first draft in the same style, no Figma frame yet | [Figma](https://www.figma.com/design/dXpZpN53pLMmkYylQwmK1H) · page "🎨 Tasarım Sistemi" |
| 8 | Login / Register / Consent | P03 | 🟨 Implemented in P03 from the tokens and the Button / input components; **no Figma frames yet**, please design or review them | |
| 9 | Transactions list & detail | P07 | ⬜ | |
| 10 | Installment schedule, Budgets, Settings | P10–P13 | ⬜ | |

## Design tokens to deliver

- Colors: primary, secondary, background, surface, text (primary/secondary), success, warning, danger, category colors (13).
- Typography: font family (must support Turkish glyphs), sizes for display/title/body/caption.
- Spacing scale, corner radii, elevation.
- Components: money text, category chip, confidence badge (HIGH/MEDIUM/LOW), deadline badge (return/warranty/installment), primary/secondary buttons, list tile, empty state.

## Constraints

- Turkish copy; money format `1.349,90 TL`; dates `09 Kasım 2026`.
- Accessible contrast (WCAG AA), min tap target 48dp, dark mode optional (not required).
- No brand logos of banks/merchants in UI assets.

## Direction v1 (2026-11-15)

- Style: calm & trustworthy. Light background, deep teal primary, generous spacing, 16–24 px card radii.
- Font: **Plus Jakarta Sans** (Turkish glyphs OK; available on Google Fonts → `google_fonts` package or bundled asset).
- Figma file: https://www.figma.com/design/dXpZpN53pLMmkYylQwmK1H — variables collection "ReceiptBox Tokens", text styles, components `Badge`, `Button`, `BottomNav`.

| Token | Value | Token | Value |
|---|---|---|---|
| color/primary | #0E5E57 | color/bg | #F5F7F6 |
| color/primary-soft | #E3F1EE | color/surface | #FFFFFF |
| color/text | #16211F | color/border | #E1E7E5 |
| color/text-muted | #5E6B68 | color/warning / soft | #B45309 / #FDF0D5 |
| color/success / soft | #047857 / #D9F3E8 | color/danger / soft | #B42318 / #FDE4E1 |
| color/info / soft | #2457C5 / #E1EAFB | radius | 8 / 12 / 16 / 24 |
| cat/grocery | #2F9E6E | cat/tech | #3B6FD8 |
| cat/food | #E08A2E | cat/transport | #8A5CD6 |
| cat/clothing | #D64F7A | cat/subscription | #2AA3B8 |

Also defined in Figma but missing from the table above (read with `get_variable_defs` on 2026-11-16): color/text-subtle `#8A9693` (inactive tab labels, placeholders), color/surface-alt `#EEF2F1` (segmented control background), color/on-primary `#FFFFFF`, cat/other `#8A9693`. Component values used by P03: BottomNav 76 high, 1 px top border, 20 px side padding, 24 px icons, Caption labels; the (+) button is 56×56, radius 18, primary, shadow `0 6 14 rgba(13,94,87,0.30)`; buttons 48 high, radius 12, secondary border 1.5; inputs 48 high, radius 12, 1 px border, label above in Label style. Only 7 of the 13 category colors exist so far (grocery, tech, food, transport, clothing, subscription, other).

Type scale: Display 32/40 ExtraBold · Title L 22/28 Bold · Title M 18/24 Bold · Title S 16/22 SemiBold · Body 15/22 · Body S 13/18 · Label 13/16 SemiBold · Caption 12/16 Medium · Overline 11/14 Bold +8%.
