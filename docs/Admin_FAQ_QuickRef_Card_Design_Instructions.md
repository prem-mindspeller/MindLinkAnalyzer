# Administrator FAQ & Laminated Booth Quick-Reference Card — Design Instructions

> **Ticket context:** MB-547 / Ekonomika Job Fair Debrief (26 Feb 2026)
> **Labels:** UX · operations · documentation
> **Priority:** High | **Parent:** MB-547 (In-Booth Student Journey) | **Related:** MB-546 (Headband Protocol)
>
> **Purpose:** Give booth administrators a single laminated card they can glance at mid-session so they never have to pause, search docs, or improvise answers while students are wearing the headband.

---

## 1  Design Overview

| Property | Specification |
|---|---|
| **Format** | Double-sided laminated card, **A4 landscape** (297 × 210 mm) |
| **Orientation** | Landscape on both sides |
| **Lamination** | 125 µm gloss pouch — wipeable with alcohol wipes between students |
| **Quantity** | Print 10 cards per booth kit (2 active + 8 spares) |
| **Tool** | Figma _or_ Canva — export PDF/PNG at 300 dpi, CMYK |
| **Font stack** | **Inter** (headings) / **Inter** or **IBM Plex Sans** (body) — both Google Fonts, free |
| **Grid** | 12-column with 16 px gutters; content lives in a 267 × 186 mm safe zone (15 mm bleed margin all around) |

---

## 2  Brand & Color Tokens

Use these exact values for consistency with the MindLink Analyzer app UI.

| Token | Hex | Usage |
|---|---|---|
| **Primary Blue** | `#2563EB` | Section headers, CTA text |
| **Dark Text** | `#1F2937` | Body copy, table text |
| **Subtitle Gray** | `#475569` | Descriptions, secondary text |
| **Card BG** | `#FFFFFF` | Content card backgrounds |
| **Page BG** | `#F8FAFC` | Overall background tint |
| **Signal Green** | `#10B981` | "Good signal" indicator |
| **Signal Yellow** | `#EAB308` | "Fair signal" indicator |
| **Signal Amber** | `#F59E0B` | "Poor / motion artifacts" indicator |
| **Signal Red** | `#EF4444` | "Not worn / critical" indicator |
| **Signal Gray** | `#94A3B8` | "Waiting…" indicator |
| **Border** | `#E2E8F0` | Card outlines, dividers |
| **Success BG** | `#ECFDF5` | Green callout card background |
| **Warning BG** | `#FFFBEB` | Yellow callout card background |
| **Danger BG** | `#FEF2F2` | Red callout card background |

---

## 3  Asset Images to Include

All images are in the repository at `assets/`. Use the originals at full resolution; crop/scale in the design tool.

| Image File | What It Shows | Where to Place on Card |
|---|---|---|
| `logo-no-text.png` | MindLink/MindSpeller logo mark | **Top-left corner** of Side A header |
| `wearinstructions.jpg` | How to position the headband on the forehead — electrode placement, strap angle | **Side A, Section 1** — "Headband Fitting" |
| `insertinstructions.jpg` | How to insert batteries / connect USB cable | **Side A, Section 1** — small inset beside power-on step |
| `onoffinstructions.jpg` | Power button location and on/off action | **Side A, Section 1** — small inset beside power-on step |
| `takeoffinstructions.jpg` | How to safely remove the headband after a session | **Side B, Section 7** — "End of Session" |
| `eye.png` / `eye-off.png` | Eyes-open / eyes-closed icons | **Side A, Section 4** — beside calibration phase labels |
| `emo_face_01.png` – `emo_face_06.png` | Six emotion face icons (Likert scale) | **Side B, Section 6** — "Self-Report Rating Scale" reference if applicable |

> **Tip for designers:** All `.jpg` instruction images have a white background — place them inside rounded-corner cards (`border-radius: 12px`, `border: 1px solid #E2E8F0`) to match the app style.

---

## 4  Card Layout — SIDE A (Primary Reference)

Side A is the **"during session"** side — the administrator keeps this facing up while a student is seated.

### Layout wireframe (landscape A4)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  [logo-no-text.png]   MINDLINK — ADMINISTRATOR QUICK REFERENCE      v2.0  │
│─────────────────────────────────────────────────────────────────────────────│
│                                                                             │
│  ┌─── 1. HEADBAND FITTING ───────┐  ┌─── 2. STUDENT FAQ ────────────────┐  │
│  │                                │  │                                    │  │
│  │  [wearinstructions.jpg]        │  │  Q: "Can I blink?"                 │  │
│  │                                │  │  A: YES — blinking is 100%         │  │
│  │  ☑ Clean electrode + skin      │  │     natural. Blink normally.       │  │
│  │  ☑ Push hair aside at Fp1      │  │     Occasional blinks don't        │  │
│  │  ☑ Moisten electrode pad       │  │     affect results.                │  │
│  │  ☑ Strap snug, NOT tight       │  │                                    │  │
│  │  ☑ Electrode ≈ 2 cm above      │  │  Q: "Can I move?"                  │  │
│  │    eyebrow center              │  │  A: Try to stay STILL. Small       │  │
│  │                                │  │     shifts are OK. Avoid head       │  │
│  │  🔄 Switch to Macrotellect     │  │     turns, jaw clenching, or       │  │
│  │     PRO flex-band if:          │  │     scratching during recording.   │  │
│  │  • Large forehead / thick hair │  │                                    │  │
│  │  • Standard band keeps         │  │  Q: "What am I supposed to do?"    │  │
│  │    slipping                    │  │  A: Follow the on-screen prompts.  │  │
│  │  • Signal stays red after      │  │     I'll tell you when to close    │  │
│  │    3 re-seats                  │  │     your eyes or watch the screen. │  │
│  │                                │  │     Just relax and pay attention.  │  │
│  │  [insertinstructions.jpg]      │  │                                    │  │
│  │  [onoffinstructions.jpg]       │  │  Q: "Is this safe?"                │  │
│  │   (small insets, side-by-side) │  │  A: Completely. It only READS      │  │
│  │                                │  │     brain waves — it sends         │  │
│  └────────────────────────────────┘  │     nothing into your head.        │  │
│                                      │     Like a thermometer for          │  │
│  ┌─── 3. SIGNAL QUALITY ─────────┐  │     brain activity.                │  │
│  │                                │  │                                    │  │
│  │  ● GREEN  → Good. Proceed.    │  │  Q: "How long does it take?"       │  │
│  │  ● YELLOW → Fair. Acceptable  │  │  A: About 5–7 minutes total.       │  │
│  │             but try to adjust. │  │     30 s eyes closed, 30 s eyes    │  │
│  │  ● AMBER  → Poor. Re-seat     │  │     open, then a few short tasks.  │  │
│  │             headband. Ask      │  │                                    │  │
│  │             student to relax   │  └────────────────────────────────────┘  │
│  │             forehead.          │                                          │
│  │  ● RED    → Not worn / no     │  ┌─── 4. SESSION FLOW CHEAT SHEET ────┐  │
│  │             contact. Reposition│  │                                     │  │
│  │             immediately.       │  │  ① Connect headband + power on     │  │
│  │  ● GRAY   → Waiting for data. │  │  ② Log in (pre-filled booth acct)  │  │
│  │             Wait 5 seconds.    │  │  ③ Check signal → GREEN?           │  │
│  │                                │  │  ④ [eye-off.png] Eyes CLOSED 30s   │  │
│  │  If stuck on RED / AMBER:      │  │  ⑤ [eye.png] Eyes OPEN 30s        │  │
│  │  1. Moisten electrode          │  │  ⑥ Cognitive tasks (on-screen)     │  │
│  │  2. Re-seat lower (2cm above   │  │  ⑦ Results → show student          │  │
│  │     brow line)                 │  │  ⑧ Remove headband, power off     │  │
│  │  3. Clear hair from electrode  │  │                                     │  │
│  │  4. Clean skin with wipe       │  │  Total time: ~5–7 min per student  │  │
│  │  5. Try PRO flex-band          │  └─────────────────────────────────────┘  │
│  │                                │                                          │
│  └────────────────────────────────┘                                          │
│                                                                             │
│  ─── GOLDEN RULE: If signal is NOT green, do NOT start calibration. ──────  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Section-by-section design notes

#### Header bar
- Full-width band, background `#2563EB`, white text.
- Left: `logo-no-text.png` at 28 px height, white-tinted.
- Center: title "MINDLINK — ADMINISTRATOR QUICK REFERENCE" in **Inter 16 pt Bold**, white.
- Right: version tag "v2.0" in Inter 11 pt, `#93C5FD` (light blue on dark).

#### Section 1 — Headband Fitting
- White card with `#E2E8F0` border, `12 px` corner radius.
- `wearinstructions.jpg` scaled to fill top of card (≈ 120 × 80 mm max, maintain aspect ratio).
- Checklist items: use ☑ character or a custom checkbox icon, Inter 11 pt, `#1F2937`.
- "Switch to PRO flex-band" sub-section: use an amber callout bar (left-border 4 px `#F59E0B`, background `#FFFBEB`).
- Bottom: small inset images `insertinstructions.jpg` and `onoffinstructions.jpg` side by side (each ≈ 50 × 35 mm), separated by 8 px gap.

#### Section 2 — Student FAQ
- White card, same styling.
- Each Q/A pair separated by a thin `#E2E8F0` divider line.
- **Q** label: Inter 11 pt SemiBold, `#1F2937`.
- **A** label: Inter 11 pt Regular, `#475569`.
- Use generous line-height (1.5) for readability at arm's length.

#### Section 3 — Signal Quality Traffic Light
- White card.
- Each status row: colored circle (16 px diameter, filled) + status name bold + action text.
- Circle colors use Signal Green / Yellow / Amber / Red / Gray tokens above.
- "If stuck on RED / AMBER" sub-section: red callout bar (left-border 4 px `#EF4444`, background `#FEF2F2`), numbered steps.

#### Section 4 — Session Flow Cheat Sheet
- White card.
- Numbered steps ①–⑧ using circled digit characters.
- Inline `eye.png` and `eye-off.png` icons at 16 × 16 px beside steps ④ and ⑤.
- Final line "Total time: ~5–7 min" in Inter 11 pt Italic, `#475569`.

#### Footer rule
- Full-width gold/amber rule line (2 px `#F59E0B`).
- "GOLDEN RULE" text centered: Inter 12 pt Bold, `#92400E` (dark amber).

---

## 5  Card Layout — SIDE B (Troubleshooting & Edge Cases)

Side B is the **"something went wrong"** side — flip the card when issues arise.

### Layout wireframe (landscape A4)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MINDLINK — TROUBLESHOOTING & EDGE CASES                         SIDE B    │
│─────────────────────────────────────────────────────────────────────────────│
│                                                                             │
│  ┌─── 5. EMG / NOISE ERRORS ─────┐  ┌─── 6. STUDENT DISTRESS ───────────┐  │
│  │                                │  │                                    │  │
│  │  "High noise detected" on      │  │  IF STUDENT WANTS TO STOP:        │  │
│  │  screen?                       │  │                                    │  │
│  │                                │  │  1. Say "No problem at all."       │  │
│  │  ✦ Ask: "Can you relax your   │  │  2. Click ✕ on the task window    │  │
│  │    forehead? Unclench jaw."    │  │     or press Back to end the       │  │
│  │  ✦ Move student's phone       │  │     current recording.             │  │
│  │    >30 cm away from headband   │  │  3. Gently remove headband.       │  │
│  │  ✦ Check for laptop charger   │  │  4. Reassure:                      │  │
│  │    cable near the headband     │  │     "This is voluntary. Your       │  │
│  │  ✦ Re-seat headband lower     │  │      data will not be used."       │  │
│  │    on forehead                 │  │  5. Log the incident (student      │  │
│  │  ✦ Wait 5 s — transient       │  │     initials + time) in the       │  │
│  │    bursts often self-resolve   │  │     booth incident sheet.         │  │
│  │                                │  │                                    │  │
│  │  If noise persists >30 s:      │  │  IF STUDENT IS ANXIOUS BUT        │  │
│  │  → Power-cycle device          │  │  WILLING TO CONTINUE:             │  │
│  │  → Re-login through app        │  │                                    │  │
│  │  → Switch to PRO flex-band     │  │  ✦ "It only reads — like a        │  │
│  │                                │  │    fitness tracker for your        │  │
│  │  WARNING MESSAGES EXPLAINED:   │  │    brain."                         │  │
│  │                                │  │  ✦ "You can stop any time."       │  │
│  │  "Not Worn"                    │  │  ✦ "Just relax and breathe        │  │
│  │  → Electrode not touching skin │  │    normally."                      │  │
│  │                                │  │  ✦ Offer water, take a 30-second  │  │
│  │  "Demo signal detected"        │  │    break before restarting.       │  │
│  │  → Device streaming test data; │  │                                    │  │
│  │    not real EEG. Reconnect.    │  │  NEVER force continuation.        │  │
│  │                                │  │  Student wellbeing > data.         │  │
│  │  "Signal: Waiting…"            │  │                                    │  │
│  │  → Normal on startup. Wait     │  └────────────────────────────────────┘  │
│  │    5-10 seconds for buffer     │                                          │
│  │    to fill.                    │  ┌─── 8. DEVICE RECONNECTION ─────────┐  │
│  │                                │  │                                     │  │
│  └────────────────────────────────┘  │  If device disconnects mid-session: │  │
│                                      │                                     │  │
│  ┌─── 7. END OF SESSION ─────────┐  │  1. Switch OFF the BrainLink       │  │
│  │                                │  │     amplifier (hold power 2 s)     │  │
│  │  [takeoffinstructions.jpg]     │  │  2. Wait 3–5 seconds              │  │
│  │                                │  │  3. Switch ON the amplifier        │  │
│  │  1. Show the student their     │  │  4. In the app, click ← Back      │  │
│  │     results screen briefly     │  │     until you reach Login screen   │  │
│  │  2. Click Export if needed     │  │  5. Log in again — this clears    │  │
│  │  3. Gently remove headband     │  │     stale data and re-establishes │  │
│  │  4. Power OFF the device       │  │     the serial connection.        │  │
│  │  5. Wipe electrode + headband  │  │                                     │  │
│  │     with alcohol wipe          │  │  If still won't connect:           │  │
│  │  6. Place headband on stand    │  │  ✦ Try different USB port          │  │
│  │     ready for next student     │  │  ✦ Restart the app                 │  │
│  │                                │  │  ✦ Check battery > 20%             │  │
│  │  Between students: ~30 sec     │  │                                     │  │
│  │  turnaround target             │  └─────────────────────────────────────┘  │
│  │                                │                                          │
│  └────────────────────────────────┘  ┌─── 9. NETWORK / LOGIN ISSUES ──────┐  │
│                                      │                                     │  │
│                                      │  ✦ Unblock the .exe (right-click   │  │
│                                      │    → Properties → Unblock)         │  │
│                                      │  ✦ Allow through firewall          │  │
│                                      │  ✦ Needs HTTPS to:                 │  │
│                                      │    en.mindspeller.com              │  │
│                                      │    nl.mindspeller.com              │  │
│                                      │  ✦ On campus Wi-Fi, ask IT to     │  │
│                                      │    whitelist the URLs above        │  │
│                                      │                                     │  │
│                                      └─────────────────────────────────────┘  │
│                                                                             │
│  ─── REMEMBER: Green signal FIRST. No green = no calibration. ────────────  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Section-by-section design notes

#### Header bar
- Same styling as Side A but text reads "TROUBLESHOOTING & EDGE CASES" and "SIDE B" on the far right.

#### Section 5 — EMG / Noise Errors
- White card.
- Bullet items use ✦ (four-pointed star) for visual weight.
- "WARNING MESSAGES EXPLAINED" sub-heading: Inter 10 pt Bold Uppercase, `#1F2937`, with a 1 px `#E2E8F0` rule above.
- Each warning message name in backtick-style monospace (`IBM Plex Mono 10 pt`, `#991B1B` dark red) followed by → explanation in regular text.

#### Section 6 — Student Distress Protocol
- **Critical section** — use `#FEF2F2` (danger BG) for the entire card background to visually distinguish it as high-priority.
- Left border: 4 px solid `#EF4444`.
- "NEVER force continuation. Student wellbeing > data." — Inter 11 pt Bold Italic, `#991B1B`.
- Numbered steps for "wants to stop" and bullet points for "anxious but willing."

#### Section 7 — End of Session
- White card.
- `takeoffinstructions.jpg` at top of card (≈ 100 × 65 mm).
- Numbered cleanup steps.
- "~30 sec turnaround target" in Inter 10 pt Italic, `#475569`, bottom of card.

#### Section 8 — Device Reconnection
- White card.
- Numbered steps for the power-cycle procedure.
- "If still won't connect" sub-section in amber callout bar.

#### Section 9 — Network / Login Issues
- Compact white card.
- URL text in `IBM Plex Mono 10 pt`.

#### Footer rule
- Same amber rule + reminder text as Side A.

---

## 6  Typography Specifications

| Element | Font | Weight | Size | Color | Line-height |
|---|---|---|---|---|---|
| Card header bar title | Inter | Bold (700) | 16 pt | `#FFFFFF` | 1.2 |
| Section title | Inter | SemiBold (600) | 13 pt | `#1F2937` | 1.3 |
| Body text | Inter | Regular (400) | 11 pt | `#1F2937` | 1.5 |
| Secondary / description | Inter | Regular (400) | 11 pt | `#475569` | 1.5 |
| FAQ Question | Inter | SemiBold (600) | 11 pt | `#1F2937` | 1.5 |
| FAQ Answer | Inter | Regular (400) | 11 pt | `#475569` | 1.5 |
| Warning name | IBM Plex Mono | Medium (500) | 10 pt | `#991B1B` | 1.4 |
| Callout / golden rule | Inter | Bold (700) | 12 pt | `#92400E` | 1.3 |
| Step number circles | — | — | 14 pt | `#2563EB` | — |
| Footer version tag | Inter | Regular (400) | 9 pt | `#93C5FD` | 1.2 |

---

## 7  Figma Implementation Notes

1. **Create a Frame**: 297 × 210 mm (A4 Landscape). Set fill to `#F8FAFC`.
2. **Auto-layout**: Use vertical auto-layout on the main frame with 16 px padding. Nest two horizontal auto-layout rows for the 2-column card grid.
3. **Components**: Create a reusable `SectionCard` component — auto-layout vertical, fill white, border `#E2E8F0` 1 px, corner radius 12 px, padding 16 px.
4. **Callout variant**: Duplicate `SectionCard`, change left border to 4 px colored, background to the relevant BG token.
5. **Traffic light dots**: Use ellipse shapes 16 × 16 px, fill with signal color tokens. Group into a `SignalIndicator` component.
6. **Image placement**: Import assets at 2× resolution (retina). Use `Fill` mode in frames — never stretch. Apply 12 px corner radius clip.
7. **Two pages**: Create a second identical frame for Side B. Link them in a Figma page called "Quick Reference Card".
8. **Export**: Export each frame as PDF (300 dpi) with bleed marks if needed, or as PNG at 2× for Canva import.

### Figma component tree
```
Quick Reference Card
├── Side A (Frame 297×210mm)
│   ├── Header Bar (auto-layout horizontal)
│   │   ├── Logo (logo-no-text.png)
│   │   ├── Title Label
│   │   └── Version Label
│   ├── Content Grid (auto-layout horizontal, gap 16px)
│   │   ├── Left Column (auto-layout vertical, gap 16px)
│   │   │   ├── Section Card: Headband Fitting
│   │   │   │   ├── Image: wearinstructions.jpg
│   │   │   │   ├── Checklist items (5×)
│   │   │   │   ├── Callout: PRO flex-band
│   │   │   │   └── Inset images row (insert + onoff)
│   │   │   └── Section Card: Signal Quality
│   │   │       ├── Traffic light rows (5×)
│   │   │       └── Callout: Stuck on RED
│   │   └── Right Column (auto-layout vertical, gap 16px)
│   │       ├── Section Card: Student FAQ (6 Q&A pairs)
│   │       └── Section Card: Session Flow Cheat Sheet
│   └── Footer Rule + Golden Rule text
│
└── Side B (Frame 297×210mm)
    ├── Header Bar
    ├── Content Grid
    │   ├── Left Column
    │   │   ├── Section Card: EMG / Noise Errors
    │   │   └── Section Card: End of Session
    │   │       └── Image: takeoffinstructions.jpg
    │   └── Right Column
    │       ├── Section Card: Student Distress (danger bg)
    │       ├── Section Card: Device Reconnection
    │       └── Section Card: Network / Login Issues
    └── Footer Rule + Reminder text
```

---

## 8  Canva Implementation Notes

1. **Template**: Start with "Custom Size" → 297 × 210 mm (or 11.69 × 8.27 in).
2. **Background**: Set page background to `#F8FAFC`.
3. **Elements**: Use Canva's rectangle shape with 12 px corner radius, white fill, and thin border for section cards.
4. **Grid**: Use Canva's built-in grid or manually position two equal-width columns with 16 px gap.
5. **Images**: Upload all assets from `assets/` folder. Use "Crop" to clip images into rounded rectangles.
6. **Colored dots**: Use Canva circle elements, 16 px, filled with signal color tokens.
7. **Callout bars**: Rectangle with the callout BG color + a narrow tall rectangle on the left edge as the accent border.
8. **Fonts**: Search for "Inter" in Canva fonts (available natively). "IBM Plex Mono" may need to be uploaded as a brand font.
9. **Pages**: Create Page 1 = Side A, Page 2 = Side B.
10. **Export**: Download as "PDF Print" (300 dpi, CMYK, crop marks enabled).

---

## 9  Full Text Content — Side A

Below is the exact copy to place in the design. Designers should use this verbatim.

---

### HEADER
**MINDLINK — ADMINISTRATOR QUICK REFERENCE** &emsp; v2.0

---

### 1. HEADBAND FITTING

☑ Clean electrode contacts with a soft cloth
☑ Push hair aside from the forehead electrode area
☑ Moisten the electrode pad lightly (finger-dab of water or saline)
☑ Place headband so electrode sits ~2 cm above the center of the eyebrows
☑ Adjust strap so it's snug but NOT tight — no red marks on skin

**When to switch to the Macrotellect PRO flex-band:**
- Student has a large forehead or thick/curly hair that lifts the standard band
- Standard band keeps slipping after 2 re-seats
- Signal stays RED or AMBER after 3 repositioning attempts
- Student reports discomfort with the rigid headband

---

### 2. COMMON STUDENT QUESTIONS

**Q: "Can I blink?"**
A: Yes — blink normally. Everyone blinks. Our software filters out blink artifacts. Trying NOT to blink actually creates more noise.

**Q: "Can I move?"**
A: Try to stay as still as you comfortably can. Small natural shifts are fine. Avoid turning your head, clenching your jaw, raising your eyebrows, or scratching during a recording segment. Between segments you can stretch.

**Q: "What am I supposed to do?"**
A: Just follow the instructions on screen. I'll tell you when to close your eyes and when to open them. During the tasks, the screen will show you exactly what to do. Just relax and pay attention.

**Q: "Is this safe? Does it send electricity into my head?"**
A: Completely safe. It only READS your natural brain waves — like a thermometer reads temperature. It sends nothing into your head. It's the same technology used in hospitals and sleep labs.

**Q: "How long does this take?"**
A: About 5 to 7 minutes total. First 30 seconds with eyes closed, then 30 seconds with eyes open, then a few short cognitive tasks on screen.

**Q: "What if I mess up a task?"**
A: There's no right or wrong answer — we're measuring your brain's natural response, not performance. Just do your best and don't worry about mistakes.

---

### 3. SIGNAL QUALITY — TRAFFIC LIGHT

| Color | Status | What to Do |
|---|---|---|
| 🟢 GREEN | Good signal | Proceed with calibration |
| 🟡 YELLOW | Fair signal | Acceptable — try adjusting headband for green |
| 🟠 AMBER | Poor signal / motion artifacts | Re-seat headband. Ask student to relax forehead and jaw |
| 🔴 RED | Not worn / no contact | Electrode is not touching skin — reposition immediately |
| ⚪ GRAY | Waiting for data | Normal on startup — wait 5–10 seconds |

**If stuck on RED or AMBER:**
1. Moisten the electrode pad
2. Re-position lower on the forehead (about 2 cm above brow line)
3. Clear any hair from under the electrode
4. Clean the skin with an alcohol wipe
5. Switch to the PRO flex-band

---

### 4. SESSION FLOW

① Connect headband via USB + power ON
② Log in (use pre-filled booth account)
③ Check Live EEG → wait for GREEN signal
④ 👁️‍🗨️ Eyes CLOSED — 30 seconds (say "Close your eyes and relax")
⑤ 👁️ Eyes OPEN — 30 seconds (say "Open your eyes and look at the screen")
⑥ Cognitive tasks — follow on-screen prompts
⑦ Show student their results
⑧ Remove headband, power OFF, wipe down

**Total time per student: ~5–7 minutes**

---

### GOLDEN RULE
**If signal is NOT green, do NOT start calibration.**

---

## 10  Full Text Content — Side B

---

### HEADER
**MINDLINK — TROUBLESHOOTING & EDGE CASES** &emsp; SIDE B

---

### 5. EMG / NOISE ERRORS

**If "High noise detected" appears on screen:**

✦ Ask the student: "Can you relax your forehead? Try to unclench your jaw."
✦ Move the student's phone or smartwatch >30 cm away from the headband
✦ Check that the laptop charger cable is not draped near the headband
✦ Re-seat headband lower on the forehead
✦ Wait 5 seconds — brief noise bursts often self-resolve

**If noise persists for more than 30 seconds:**
→ Power-cycle the device (OFF → wait 3 sec → ON)
→ Navigate back to Login and re-authenticate
→ Try the Macrotellect PRO flex-band

**Warning messages explained:**

| Message | Meaning | Action |
|---|---|---|
| "Not Worn" | Electrode has no skin contact | Reposition headband |
| "Demo signal detected" | Device is streaming internal test data, not real EEG | Reconnect the device via USB and power-cycle |
| "Signal: Waiting…" | App is filling its data buffer | Normal — wait 5–10 seconds |
| "High noise detected" | Muscle tension or electrical interference | Follow EMG steps above |

---

### 6. IF A STUDENT WANTS TO STOP

1. Say calmly: **"No problem at all."**
2. Click ✕ on the task window or press **← Back** to end the current recording
3. Gently remove the headband
4. Reassure the student: **"This is completely voluntary. Your data will not be used."**
5. Log the incident on the booth incident sheet (student initials + time)

**If the student is anxious but willing to continue:**
✦ "It only reads — like a fitness tracker for your brain."
✦ "You can stop at any time, just say the word."
✦ "Just relax and breathe normally."
✦ Offer water. Take a 30-second break before restarting.

> ⚠️ **NEVER force continuation. Student wellbeing is more important than data.**

---

### 7. END OF SESSION

1. Show the student their results screen briefly
2. Click **Export** if data collection is needed
3. Gently remove the headband
4. Power OFF the device
5. Wipe the electrode and headband with an alcohol wipe
6. Place headband on the charging stand, ready for next student

**Target turnaround between students: ~30 seconds**

---

### 8. DEVICE RECONNECTION (MID-SESSION)

If the device disconnects during a session:

1. Switch **OFF** the BrainLink amplifier (hold power button 2 seconds)
2. Wait **3–5 seconds**
3. Switch **ON** the amplifier
4. In the app, click **← Back** repeatedly until you reach the Login screen
5. **Log in again** — this clears stale data and re-establishes the serial connection

**If it still won't connect:**
✦ Try a different USB port
✦ Restart the MindLink application entirely
✦ Verify battery level is above 20%
✦ Check USB cable is fully seated

---

### 9. NETWORK / LOGIN ISSUES

✦ **Windows security block:** Right-click the .exe → Properties → check "Unblock" → OK
✦ **Firewall:** Allow BrainCompanion.exe through Windows Firewall (both Private and Public)
✦ **Required URLs** (must be reachable via HTTPS):
  - `en.mindspeller.com`
  - `nl.mindspeller.com`
✦ **Campus / corporate Wi-Fi:** Ask venue IT to whitelist the URLs above before the event
✦ **Run built-in diagnostics:** The app has a "Run Diagnostics" button — save `diagnostic_results.txt` for support

---

### REMINDER
**Green signal FIRST. No green = no calibration.**

---

## 11  Print & Production Checklist

- [ ] Verify all text fits within the 267 × 186 mm safe zone (15 mm from each edge)
- [ ] Check that body text is ≥ 10 pt — anything smaller is hard to read at arm's length
- [ ] Test color contrast for colorblind accessibility (signal colors have text labels as backup)
- [ ] Export at 300 dpi, CMYK color space
- [ ] Print one test copy on standard paper before laminating the batch
- [ ] Laminate with 125 µm gloss pouches (A4 landscape size: 303 × 216 mm pouch)
- [ ] Round the laminated corners with a corner punch (6 mm radius) to prevent sharp edges
- [ ] Include 2 cards per booth station + 8 spares in the event kit
- [ ] Store flat, not rolled — laminated cards warp if rolled

---

## 12  Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-03-05 | Initial design based on Ekonomika Job Fair debrief (26 Feb 2026) |

---

## 13  Appendix A — Asset File Reference

All files referenced in this document are relative to the repository root:

```
assets/
├── logo-no-text.png          → Header branding
├── wearinstructions.jpg      → Headband fitting visual (Side A §1)
├── insertinstructions.jpg    → Battery/USB insert visual (Side A §1)
├── onoffinstructions.jpg     → Power on/off visual (Side A §1)
├── takeoffinstructions.jpg   → Headband removal visual (Side B §7)
├── eye.png                   → Eyes-open icon (Side A §4)
├── eye-off.png               → Eyes-closed icon (Side A §4)
├── emo_face_01.png           → Emotion scale face 1 (optional, self-report)
├── emo_face_02.png           → Emotion scale face 2
├── emo_face_03.png           → Emotion scale face 3
├── emo_face_04.png           → Emotion scale face 4
├── emo_face_05.png           → Emotion scale face 5
├── emo_face_06.png           → Emotion scale face 6
├── splash.png                → App splash (optional branding)
├── favicon.ico               → Not used on card
├── NUM_FORM.png              → Not used on card
├── ORDER_SURPRISE.png        → Not used on card
└── curiosity_clip_01.mp4     → Not used on card
```
