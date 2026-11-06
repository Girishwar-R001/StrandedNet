---
name: Calm Horizon
colors:
  surface: '#f8f9ff'
  surface-dim: '#ccdbf4'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e6eeff'
  surface-container-high: '#dde9ff'
  surface-container-highest: '#d5e3fd'
  on-surface: '#0d1c2f'
  on-surface-variant: '#3f4850'
  inverse-surface: '#233144'
  inverse-on-surface: '#ebf1ff'
  outline: '#707881'
  outline-variant: '#bfc7d2'
  surface-tint: '#006398'
  primary: '#006194'
  on-primary: '#ffffff'
  primary-container: '#007bb9'
  on-primary-container: '#fdfcff'
  inverse-primary: '#93ccff'
  secondary: '#565e74'
  on-secondary: '#ffffff'
  secondary-container: '#dae2fd'
  on-secondary-container: '#5c647a'
  tertiary: '#006948'
  on-tertiary: '#ffffff'
  tertiary-container: '#00855d'
  on-tertiary-container: '#f5fff7'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#cce5ff'
  primary-fixed-dim: '#93ccff'
  on-primary-fixed: '#001d31'
  on-primary-fixed-variant: '#004b73'
  secondary-fixed: '#dae2fd'
  secondary-fixed-dim: '#bec6e0'
  on-secondary-fixed: '#131b2e'
  on-secondary-fixed-variant: '#3f465c'
  tertiary-fixed: '#85f8c4'
  tertiary-fixed-dim: '#68dba9'
  on-tertiary-fixed: '#002114'
  on-tertiary-fixed-variant: '#005137'
  background: '#f8f9ff'
  on-background: '#0d1c2f'
  surface-variant: '#d5e3fd'
typography:
  headline-xl:
    fontFamily: Plus Jakarta Sans
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 30px
    fontWeight: '700'
    lineHeight: 38px
    letterSpacing: -0.015em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: 0em
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-lg:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.04em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-desktop: 1.5rem
  margin: 1rem
  margin-tablet: 2rem
  margin-desktop: 3rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

### Personality & Purpose
The design system powers an emergency travel disruption recovery interface built specifically for stressed, fatigued, and disoriented passengers. Its brand ethos centers on radical clarity, grounded reassurance, and proactive transparency. Every viewport must actively de-escalate crisis anxiety through order, predictable visual cadences, and immediate path-to-resolution signposts.

### Design Movement: Functional Serenity
Combining utilitarian structural discipline with humanist reassurance, the aesthetic blends Scandinavian minimalism with mission-critical aviation instrumentation. The interface rejects frenetic micro-interactions, sensory overload, and ambiguous decorative layers. It relies instead on structured information architecture, generous negative space, crisp visual hierarchies, and clear status feedback to instill confidence under pressure.

### Emotional Target
The user experience evokes feelings of being safe, supported, and clearly directed. Interfaces must never look panicked, overly decorative, or chaotic. Tone is authoritative, calm, and unmistakably dependable.

## Colors

### Palette Strategy
The color system operates with strict semantic rules to avoid sensory confusion in high-stress moments:

- **Primary Canvas & Slate Hierarchy**: The grounding anchor is Deep Slate (`#0F172A` for primary text and high-contrast anchors, `#1E293B` for structural elements, and `#334155` for secondary content).
- **Aviation Blues**: `#0284C7` (Sky Primary) and `#2563EB` (Cobalt Accent) serve as focus states, primary progress indicators, and actionable triggers, paired with `#0EA5E9` for informational highlights.
- **Resolution Mint & Emerald**: `#059669` and `#10B981` are reserved exclusively for resolved issues, confirmed rebookings, active boarding passes, and secure voucher states.
- **Disruption Warm Amber**: `#D97706` handles transit alerts, missed connections, delay warnings, and time-critical actions without inducing panic like severe crimson errors.
- **Surfaces**: Ultra-clean `#FFFFFF` and muted `#F8FAFC` establish a low-fatigue, glare-resistant foundation optimized for chaotic terminal lighting.

### Contrast & Accessibility
All interactive text combinations strictly enforce WCAG AA compliance (4.5:1 for body copy and 3:1 for large display headlines and key graphic controls). Status colors are never presented without companion iconography or clear textual tags.

## Typography

### Structural Pairings
- **Headlines (Plus Jakarta Sans)**: Provides human warmth, balanced apertures, and friendly geometric clarity that softens high-stress news without feeling casual.
- **Body & Labels (Inter)**: Delivers exceptional legibility on degraded mobile screens, smudged displays, and bright glare conditions. Tabular numbers are enabled for flight codes, departure counters, gate changes, and compensation totals.

### Hierarchy & Legibility Rules
- Never set critical recovery actions or emergency status codes below `14px` (`body-sm`).
- Maintain a minimum of `1.4x` line-height on all body prose to reduce line-skipping when reading on moving airport transit shuttles or terminal escalators.

## Layout & Spacing

### Layout Architecture
The design system implements a strict responsive fluid grid:
- **Mobile (< 768px)**: 4-column layout with `1rem` margins and `1rem` gutters. Elements stack vertically into single-column flows to preserve continuous cognitive focus.
- **Tablet (768px – 1023px)**: 8-column layout with `2rem` margins and `1rem` gutters. Support panels sit alongside the primary status tracker.
- **Desktop (≥ 1024px)**: 12-column layout with a maximum container boundary of `1280px`, `3rem` margins, and `1.5rem` gutters. Content centers cleanly to prevent extreme reading spans.

### Spacing Discipline
Visual rhythm follows a strict 4px base increment. Padding inside actionable status surfaces always prioritizes breathing room (`space-lg`), keeping tap regions isolated and preventing destructive mis-taps in rushed physical environments.

## Elevation & Depth

### Tonal Hierarchy over Heavy Shadows
In high-stress utility platforms, simulated lighting physics and heavy black drop-shadows create visual fatigue and muddy mobile screens. The elevation model prioritizes subtle surface tonal layering over drop shadows:

- **Level 0 (Canvas Base)**: `#F8FAFC` serves as the bedrock substrate.
- **Level 1 (Card & Section Containers)**: `#FFFFFF` with a crisp structural hairline border (`1px solid #E2E8F0`).
- **Level 2 (Active Focus & Sticky Trays)**: `#FFFFFF` elevated with a faint ambient slate halo (`0 4px 20px -2px rgba(15, 23, 42, 0.06)`), bounded by an accent border.
- **Level 3 (Emergency Modals & Critical Overlays)**: `#FFFFFF` surfaced over a frosted slate scrim (`#0F172A` at 45% opacity), accompanied by an ambient anchor shadow (`0 12px 32px -4px rgba(15, 23, 42, 0.12)`).

## Shapes

### Form Geometry
The shape language uses moderate, balanced radii (`roundedness: 2`, `0.5rem` base, up to `1rem` on container cards) to soften visual tension while maintaining clean, predictable edges. Fully round pill shapes are reserved exclusively for compact status badges, category chips, and floating urgent phone/chat buttons.

## Components

### Buttons & Interactive Touch Targets
- **Dimensions**: All touchable items have a strict minimum physical footprint of `44x44px` (`48px` default on mobile) with generous interactive hit-slop.
- **Primary Recovery CTA**: Filled Sky Blue (`#0284C7`), bold label, `#FFFFFF` text. Used only for the single most important next step (e.g., "Confirm Hotel Voucher", "Accept New Flight").
- **Secondary Action**: Bordered Deep Slate (`#1E293B`), transparent background, hover tint (`#F1F5F9`).
- **Critical / Reject Action**: Muted slate ghost button or warm amber accent outline. Harsh red styling is avoided to prevent panic.

### Status Chips & Badges
- **Confirmed / Resolved**: Background `#ECFDF5`, border `#A7F3D0`, text `#065F46`, paired with an explicit check icon.
- **Disrupted / Pending**: Background `#FFFBEB`, border `#FDE68A`, text `#92400E`, accompanied by an alert icon and active time countdown.
- **Information / Transit**: Background `#F0F9FF`, border `#BAE6FD`, text `#0369A1`.

### Disruption Resolution Cards
- **Structure**: High-contrast header with carrier/disruption ID, bold departure/arrival timeline, and an isolated action strip pinned to the bottom.
- **Styling**: `#FFFFFF` background, `1px solid #E2E8F0`, `1rem` corner radius, `space-lg` internal padding. Status banners span full width at the top edge of the card.

### Input Fields
- Minimum height of `48px` to facilitate thumb interactions while walking.
- Background `#FFFFFF`, border `1.5px solid #CBD5E1`, text `#0F172A`.
- Active focus state features an explicit `2px` aviation blue ring (`#0284C7`) with a `2px` offset.

### Flight / Connection Stepper
- Sequential itinerary tracks linked with a continuous vertical or horizontal `2px` connective line.
- Nodes reflect exact state: checkmark for cleared legs, blinking amber node for disrupted segments, and dashed lines for tentative rebooked routes.