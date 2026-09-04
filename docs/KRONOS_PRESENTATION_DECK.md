# 🎤 PROJECT KRONOS — Presentation Deck Playbook (PPT)

> Build this in **Canva / Google Slides / PowerPoint** in 16:9. Each slide below has:
> **ON-SLIDE** (exact copy, keep bullets short) · **VISUAL** (what image/diagram goes where) · **SPEAKER NOTES** (what to say).
> Replace any `📷 [photo]` with your real photos. Diagrams = use **draw.io / PowerPoint shapes / Canva diagrams** (AI image tools garble text in diagrams — see Part C).

**Design DNA (use everywhere):**
- Palette: deep forest green `#14532D` · leaf green `#22C55E` · cream `#FAF7F0` · amber accent `#F59E0B` · charcoal `#1F2937`
- Fonts: headings **Poppins Bold**, body **Inter** (both free on Google Fonts / Canva)
- Layout rule: 1 big idea per slide · max 5 bullets · numbers > words

---

# PART A — SLIDE-BY-SLIDE CONTENT

## Slide 1 · Title
**ON-SLIDE:**
- 🌱 Logo (top-center)
- **PROJECT KRONOS**
- *Smart Soil Intelligence & Precision Agronomy*
- "A digital agronomist in every farmer's pocket."
- `Inter-College Competition on Prototype Design for Mankind · AI/ML based Instrumentation Systems`
- **Team Kronos** · Kolkata, WB · teamkronos.2025@gmail.com

**VISUAL:** Full-bleed hero image (farmer holding the probe in a field at golden hour) with a dark-green gradient overlay + white text on top. *(Prompt in Part C, Image 1.)*

**SPEAKER (≈30s):** "Good morning. We are Team Kronos. Every year, smallholder farmers lose up to 40% of their crops to decisions made in the dark — guessing how much fertilizer, when to water, when disease will strike. We built a device that puts a digital agronomist in every farmer's pocket."

---

## Slide 2 · The Problem
**ON-SLIDE (title):** `Farming is flying blind`
**4 cards:**
1. 🧪 **2–4 week lab delays** — soil tests return long after the season has moved on
2. 📟 **Raw numbers, no answers** — probes say "µS/cm", not "apply 35 kg urea"
3. 🌧️ **One-size-fits-all** — blanket fertilizer & flood irrigation ignore micro-climate
4. 🍂 **Disease found too late** — foliar collapse = up to 40% yield loss

**Footer banner:** *"Farmers don't need more data. They need answers."*

**VISUAL:** 4 icon cards in a row (2×2 on smaller screens), amber icons, cream background.

**SPEAKER (≈45s):** "Today's farmer has two extremes: a lab test that takes weeks, or an IoT probe that spews raw numbers nobody can act on. Meanwhile the whole field gets the same dose of fertilizer — wasting 30–45% of it — and diseases are only noticed when the leaf has already collapsed. The digital divide makes it worse: dashboards assume literacy and English."

---

## Slide 3 · Our Solution (Overview)
**ON-SLIDE (title):** `KRONOS — The Answer Loop`
**3-step flow strip (left → right):**
1. ⚙️ **Sense** — ESP32-S3 + 7-in-1 probe reads N, P, K, pH, EC, moisture, temp every second
2. 🧠 **Think** — deterministic soil science + Llama 3.3 70B AI fuses soil + 14-day weather
3. 📲 **Act** — exact kg/acre doses, irrigation timing, risk alerts — in the farmer's language

**Big statement (bottom):** *"From soil chemistry → farmer decision in seconds."*

**VISUAL:** 3 numbered cards with arrows between them; keep it flat and simple.

**SPEAKER (≈30s):** "KRONOS closes the loop. One rugged device senses the soil continuously. Our engine — a mix of calibrated soil science and large-language-model AI — translates that into exact decisions. And we deliver it through a dashboard and chatbot that speaks the farmer's language, emoji-rich and plain."

---

## Slide 4 · How It Works — The 4-Stage Chain
**ON-SLIDE (title):** `From soil to decision`
**4 stages (horizontal chevrons):**
1. **SOIL → DATA** — 7 parameters · every 1 second · Wi-Fi to cloud
2. **DATA → INSIGHTS** — NPK bands · soil type · 6 risk alerts
3. **INSIGHTS → ADVICE** — AI prescriptions + weather fusion
4. **ADVICE → ACTION** — farmer applies exact dose & timing

**VISUAL:** Big chevron/diagram across the slide *(Diagram Prompt A)*. This is your money diagram — make it large.

**SPEAKER (≈40s):** "Four stages. The probe reads seven soil parameters every second and streams them to the cloud. Raw readings become soil type, nutrient bands and risk alerts. Then AI — fused with a 14-day weather forecast — turns that into stage-specific advice. And the farmer acts: exact kilograms per acre, exact timing."

---

## Slide 5 · Hardware Prototype
**ON-SLIDE (title):** `The field node — under $65 of hardware`
**Left:** 📷 [photo: hardware node assembly] *(slot `figure1`)*
**Right — 6 highlight chips:**
- ESP32-S3 microcontroller (240 MHz dual-core)
- 7-in-1 RS-485 soil probe — 7 parameters in <15 s, no lab
- NEO-M8N GNSS *(v3.0 — GPS tagging)*
- OLED live display · Li-Po 5–10 Ah + solar
- IP65 rugged enclosure — field-ready
- ⚡ <250 mA active draw — 7–14 days on one charge

**SPEAKER (≈45s):** "This is the heart of it: an ESP32-S3 with an industrial 7-in-1 probe — nitrogen, phosphorus, potassium, pH, salinity, moisture and temperature, all in one push, no reagents. It shows readings on its own OLED, runs on battery and solar for up to two weeks, and the whole node costs under sixty-five dollars."

---

## Slide 6 · System Architecture
**ON-SLIDE (title):** `System architecture`
**Center:** 📷 [diagram: full pipeline] *(Diagram Prompt B — draw.io)*
**Caption strip (bottom):** `ESP32-S3 → InfluxDB Cloud → AI Brain → Dashboard & Chatbot`

**SPEAKER (≈30s):** "End to end: the node pushes readings over Wi-Fi to InfluxDB Cloud, materialized every second into local CSV and Parquet stores. Our Python brain applies rolling calibration, the deterministic agronomy engine, weather fusion, and the LLM — then serves the dashboard and chatbot APIs. In v3.0 we add spatial mapping, disease vision, multi-user auth, and alerts."

---

## Slide 7 · AI Precision Dosing (Killer Slide)
**ON-SLIDE (title):** `Not "apply urea" — exact prescriptions`
**Example advisory card (mock dashboard snippet):**
> 🌾 **Wheat · Day 25 (tillering)**
> - Urea **30–40 kg/acre** — split into 2 doses
> - SSP **40–50 kg/acre** basal
> - Irrigate 6–8 cm at tillering
> - ⚠ Fungal risk: 30–38°C + 68% humidity — monitor

**Caption:** *Chemical + organic + foliar alternatives, matched to crop stage.*

**VISUAL:** Mock the card in Figma/Canva or screenshot from your real app — do NOT use AI image generation for this (text will garble).

**SPEAKER (≈45s):** "This is what separates us from advisory apps. Not 'apply urea' — but thirty to forty kilograms per acre, split into two doses, at the right growth stage, with organic and foliar alternatives, plus the risk warning that matters this week. That's a prescription, not a suggestion."

---

## Slide 8 · Weather-Fused Agronomy
**ON-SLIDE (title):** `14 days ahead, not 14 days late`
- 🌱 **Sowing windows** — 3+ consecutive dry, moderate-temp days
- 🚫 **Spray blackouts** — don't spray before rain; avoid runoff
- 🔥 **Heat stress alerts** — >36°C → pre-dawn irrigation
- 📅 **ECMWF SEAS5** — 6-month seasonal crop planning

**VISUAL:** 📷 [photo: weather planner screen from your app] + small forecast chip row (14 day icons: 🌦️🌧️☀️).

**SPEAKER (≈30s):** "Fertilizer advice is only half the story. We fuse the soil state with a live 14-day forecast — so KRONOS tells the farmer the exact days to sow, warns when rain will wash away a spray, and flags heat stress before it burns the crop."

---

## Slide 9 · v3.0 Upgrade 1 — GPS Field Mapping
**ON-SLIDE (title):** `Map your whole field with ONE probe`
- 🚶 Walk the field — GPS-tagged readings at 10–20 spots
- 🗺️ **6 heatmap layers** — N · P · K · pH · EC · Moisture
- 🎯 **VRF zones:** *"Zone A — apply 40 kg/acre N"* · *"Zone C — skip"*
- 💰 **20–40% fertilizer cost reduction** (Variable Rate Fertilization)

**VISUAL:** 📷 [photo: heatmap from your prototype] *(slot `figure3`)* — make it the star, large on the right.

**SPEAKER (≈45s):** "Our first v3.0 upgrade: one probe becomes a whole-field mapper. The farmer walks the field with GPS; the system interpolates the readings into nutrient heatmaps. Instead of fertilizing everything, the map says zone A needs nitrogen, zone C doesn't. Studies put the fertilizer saving at twenty to forty percent — plus GPS records for subsidies and certification."

---

## Slide 10 · v3.0 Upgrade 2 — Leaf Disease Detection
**ON-SLIDE (title):** `Snap a leaf, get a cure`
- 📸 Photo → EfficientNet-B4 → disease + confidence + severity
- 💊 Full protocol: chemical + organic + timing + prevention
- 🧬 **Killer feature — soil cross-reference:**
  *"Rice Leaf Blight detected. Your soil is actively promoting it — humidity 68%, temp 33°C. Bring humidity below 55% to slow spread."*

**VISUAL:** 📷 [photo: disease scan card] *(slot `figure4`)* + small inset of soil values.

**SPEAKER (≈45s):** "Second upgrade: disease detection. Snap a leaf, get the disease, confidence, severity, and the full cure — chemical and organic. But here's the part nobody else does: we cross-reference the diagnosis with live soil data. The disease isn't random — the soil is feeding it. So we treat both the leaf and the field."

---

## Slide 11 · v3.0 Upgrade 3 — Platform & Alerts
**ON-SLIDE (title):** `Multi-farm, multi-user, always alert`
- 🔐 JWT auth + Google OAuth + farm profiles
- 🗂️ Per-farm dashboards · heatmaps · history · PDF reports
- 💧 Waterlogging zone detection — *"drain this zone within 6 hours"*
- 📲 WhatsApp/SMS alerts via Twilio · PWA (offline) · EN/BN/HI

**VISUAL:** 📷 [photo: dashboard] *(slot `figure2`)*.

**SPEAKER (≈30s):** "Third upgrade: a real platform. Farmers log in, manage multiple farms and devices, get waterlogging warnings before root damage, and receive alerts on WhatsApp — the app works offline and speaks Bengali, Hindi, and English."

---

## Slide 12 · Impact & SDG
**ON-SLIDE (title):** `Impact on the ground`
**3 big stat cards:**
- **−20–35%** fertilizer cost
- **+15–25%** crop yield
- **Thousands of litres** fresh water saved / acre / cycle
**SDG chips:** 🎯 SDG 2 · Zero Hunger | SDG 12 · Responsible Production | SDG 15 · Life on Land

**VISUAL:** Giant numbers, small supporting text. SDG badges bottom-right.

**SPEAKER (≈30s):** "The impact maps directly to three SDGs. Less fertilizer wasted — that's responsible production and less nitrate in drinking water. Higher yields with healthier soil — zero hunger. And water saved every cycle — resilience in a changing climate."

---

## Slide 13 · Cost & Feasibility
**ON-SLIDE (title):** `Premium precision, pocketbook price`
**Comparison bar (₹ scale):**
- **KRONOS node: ~₹5,200** *(< $65)* — cloud ₹0/month (free tiers)
- Commercial VRA / drone systems: **₹8,00,000+** ($10k+)
- ✅ *"Less than 1/10th the cost"*

**VISUAL:** Horizontal bar comparison (big bar vs tiny bar). Green vs gray.

**SPEAKER (≈20s):** "Commercial precision agriculture costs tens of thousands of dollars. Ours is a five-thousand-rupee node and a zero-rupee cloud stack. That's what makes it deployable for smallholders and village cooperatives."

---

## Slide 14 · Roadmap
**ON-SLIDE (title):** `v3.0 in 8 weeks`
**Horizontal timeline (6 chips):**
`Phase 1 Foundation · Wk1–2` → `Phase 2 GPS · Wk3–4` → `Phase 3 Heatmaps · Wk5` → `Phase 4 Disease AI · Wk6` → `Phase 5 Alerts · Wk7` → `Phase 6 PWA · Wk8`

**SPEAKER (≈20s):** "We've built v2.1 to production — probe to cloud to AI advisory, all working. v3.0 is an eight-week roadmap: foundation and auth, then GPS hardware, heatmap engine, disease AI, alerts, and finally the offline PWA."

---

## Slide 15 · UVP + Business Model
**ON-SLIDE (title):** `Built to last, built for all`
**Quote banner:** *"Exact fertilizer dosages and disease cures, in the farmer's language — at less than 1/10th the cost of commercial alternatives."*
**4 model rows:**
1. 🤝 **Cooperative hubs (B2B2C)** — FPOs & Panchayats share nodes across 50–100 farmers
2. 💳 **Freemium** — free diagnostics; Pro ₹99/mo (heatmaps, disease AI, PDFs)
3. 🛒 **Agri-input marketplace** — order the prescribed fertilizer, in-app
4. 🌍 **Carbon & soil-health credits** — verified data logs for green subsidies

**SPEAKER (≈30s):** "The business model keeps it humanitarian and sustainable: cooperatives buy nodes and share them, software is freemium, and the prescriptions can order the exact inputs directly. Over time, the soil data we verify becomes valuable for carbon and subsidy programs — funding the mission."

---

## Slide 16 · Thank You
**ON-SLIDE:**
- 🌱 (large logo)
- **Thank You**
- *"Closing the loop from soil chemistry to actionable farmer intelligence."*
- Team Kronos · Kolkata, WB · teamkronos.2025@gmail.com
- `Questions welcome`

**VISUAL:** Same hero image as Slide 1 (bookends the deck).

---

# PART B — TEMPLATE RECOMMENDATIONS

## Option 1 · Canva (easiest, fastest — recommended)
1. Create → **Presentation (16:9)**
2. Search templates: **"agriculture"**, **"green business"**, or **"startup pitch deck"**
3. Best bets: *"Green & Beige Minimal Agriculture"*, *"Earth Tone Business"*, *"Organic Nature Pitch Deck"*
4. Then swap: set background to cream `#FAF7F0`, titles to Poppins Bold in `#14532D`, accents to `#22C55E` / `#F59E0B`, and paste the slide content from Part A.
5. Export → **PDF** or **PowerPoint (.pptx)** for submission.

## Option 2 · Google Slides (free, no account design skills needed)
- Start from blank 16:9, apply the palette above manually.
- Add fonts: **Poppins** + **Inter** via "Add-ons → Extensis Fonts".
- Use the built-in **"Serenity"** or **"Celebration"** theme as a base and recolor to the green palette.

## Option 3 · PowerPoint (best control for diagrams)
- Built-in themes **"Ion"** / **"Retrospect"** are clean bases — then recolor via **Design → Variants → Colors** (custom green palette).
- Draw the pipeline/architecture with **Insert → Shapes → SmartArt** (chevrons for the 4-stage chain).

## Option 4 · AI-generated template — highly detailed prompt
Paste this into **Gamma.app** (or Tome / an AI designer) to generate the deck shell:

> Create a 16-slide, 16:9 startup presentation template for "PROJECT KRONOS", an agricultural-technology company that builds smart soil sensors and AI advisory for smallholder farmers in India.
>
> **Style:** modern, premium, warm-natural. Flat vector illustrations and generous white space. Photographs are secondary — iconography and typography lead. No clutter: one idea per slide, maximum 5 bullets per slide.
>
> **Color palette (exact):** deep forest green #14532D for headers and dark panels; leaf green #22C55E for accents and highlights; warm cream #FAF7F0 for slide backgrounds; amber #F59E0B reserved ONLY for alerts, "NEW" badges, and key numbers; charcoal #1F2937 for body text.
>
> **Typography:** headings in Poppins Bold (or Montserrat ExtraBold), body in Inter Regular. Large numerals (72pt+) for statistics. Keep all-caps only for small labels and eyebrow text.
>
> **Layout system:** consistent 12-column grid; title in the top-left with a small green leaf icon; thin green rule under the title; footer strip with slide number, "Team Kronos", and a small leaf logo. Define 5 slide archetypes and apply them consistently: (1) cover with full-bleed image + dark green overlay, (2) section header with big number, (3) four icon cards in a row, (4) left text / right image split, (5) full-bleed diagram or screenshot slide.
>
> **Slide archetypes to generate:** 1 cover · 1 problem (4 cards) · 1 solution flow (3 arrows) · 1 four-stage pipeline chevron · 1 hardware (text left, image right) · 1 full-width architecture diagram · 1 prescription card mockup · 1 weather planner · 3 upgrade feature slides (image right) · 1 impact with 3 giant stats · 1 cost comparison bar · 1 roadmap timeline · 1 business-model 4-row table · 1 thank-you cover.
>
> **Do NOT** use stock photos of farmers shaking hands or generic fields; prefer flat vector style. No decorative gradients that fight the text. Ensure every slide title is 30–40pt and body ≥18pt for projection readability.

---

# PART C — IMAGE & DIAGRAM GENERATION PROMPTS

> ⚠️ **Rule of thumb:** AI image generators (Midjourney, DALL·E, Ideogram, Bing) are **great for hero/illustration images and terrible for diagrams and UI screens**. For diagrams (C1) build them in **draw.io / PowerPoint / Canva** using the structure given. For UI screenshots, use your **real app** or mock in Figma/Canva.

## C1 · Diagrams — build these manually (structure provided)

**Diagram A — The 4-Stage Chain (Slide 4):**
Horizontal chevrons: `SOIL → DATA` · `DATA → INSIGHTS` · `INSIGHTS → ADVICE` · `ADVICE → ACTION`, each with a sub-line (7 parameters · 1s / NPK bands + risk / AI + weather / exact dose). Use PPT SmartArt "Chevron Process".

**Diagram B — Full Architecture (Slide 6):** 4 columns with boxes:
```
FIELD:    ESP32-S3 · 7-in-1 Probe · GNSS · OLED
STORE:    InfluxDB Cloud ──► CSV / Parquet / state
BRAIN:    Rolling calib. → NPK bands → risk → LLM (Llama 3.3 70B) + Open-Meteo
USER:     Flask API → Dashboard · Chatbot · Heatmaps
```
Colors: column headers `#14532D`, boxes white with `#22C55E` borders, arrows gray.

## C2 · AI image-generation prompts (Midjourney / DALL·E / Bing / Ideogram)

Add to any prompt: `flat vector / editorial illustration style, deep forest green #14532D and cream #FAF7F0 palette, amber #F59E0B accents, soft shadows, clean composition, no text, no words, no letters, 16:9`. *(Midjourney: append `--ar 16:9 --style raw --v 6`.)*

**Image 1 · Hero cover (Slide 1 & 16):**
> A smallholder farmer in India standing in a lush green field at golden hour, holding a small cylindrical soil probe device with a small OLED screen, one hand pressing the probe into the soil, looking at it with quiet satisfaction, a smartphone in the other hand showing a green dashboard, warm sunlight flare, shallow depth of field, documentary-photography style, warm earthy tones with deep green and amber, no text.

**Image 2 · Hardware hero illustration (Slide 5 background):**
> Isometric flat vector illustration of a rugged IoT soil sensor node: a small green circuit board microcontroller, a long stainless-steel soil probe with 7 marked segments, a small OLED display showing a green leaf icon, a battery pack, a small solar panel, and a GPS chip, floating components exploded view with dashed connection lines, deep green and cream palette with amber accents, minimal, clean, no text.

**Image 3 · Nutrient heatmap concept (Slide 9 fallback — else use your real screenshot):**
> Top-down aerial illustration of a farm field divided into irregular polygon zones, each zone colored on a gradient from light green (sufficient nutrients) to red (deficient), with small pins and a subtle grid overlay, flat vector cartographic style, cream background, deep green palette with red-to-green heat gradient, a small legend bar in the corner, no text.

**Image 4 · Leaf disease scan concept (Slide 10 fallback):**
> Close-up illustration of a farmer's hand holding a smartphone over a rice leaf with early blight spots, the phone screen showing a diagnostic overlay with a highlighted leaf outline and a small green checkmark badge, flat vector editorial style, soft depth of field, deep green and cream palette, no readable text.

**Image 5 · Dashboard concept art (Slide 11 background — subtle, behind a screenshot):**
> Abstract flat illustration of a farming data dashboard: floating cards showing a leaf icon, a droplet icon, a temperature gauge, a small line chart, and a chat bubble, arranged on a soft green gradient, subtle grid, isometric tilt, deep green, cream and amber palette, no text.

**Image 6 · Farmer + chatbot concept (Slide 3 background):**
> Flat vector illustration of a farmer in a field holding a smartphone, a large friendly chat bubble floating above the phone with a small leaf and a droplet icon inside, small icons for rain cloud, sun, and plant sprout floating around, warm cream background, deep green and amber palette, no text.

**Image 7 · Data pipeline concept art (Slide 6 side panel):**
> Abstract flat illustration of a data pipeline as a winding path through stylized terrain: a soil probe icon feeding a stream of glowing dots into a cloud icon, then into a glowing brain icon, then into a smartphone icon, connected by curved dashed lines with small sparkle nodes, deep green and cream with amber accents, no text.

**Image 8 · Waterlogging detection concept (Slide 11 optional):**
> Flat vector cross-section illustration of a farm field under rain, showing three zones: one low-lying zone with standing water and a red warning pin, one middle zone with healthy green crops, one raised dry zone with a lighter pin, an underground drainage arrow, cream background, deep green palette with amber warnings, no text.

---

## 🖼️ Photo checklist for your real assets (`assets/` folder)
| File | Where used | What to put |
|:-----|:-----------|:------------|
| `figure0_cover.jpg` | Slide 1, 16 | Hero: farmer + probe in field (or team shot) |
| `figure1_hardware_node.jpg` | Slide 5 | Your physical node build (top-down, good light) |
| `figure2_dashboard.png` | Slide 11 | Live dashboard screenshot |
| `figure3_heatmap.png` | Slide 9 | Heatmap / field-mapping screenshot |
| `figure4_disease_scan.png` | Slide 10 | Disease-scan result card screenshot |
| — | Slide 7 | Advisory card screenshot (AI dosing example) |
| — | Slide 8 | Weather planner screenshot |

---

<div align="center">

**Next step:** pick Option 1–4 in Part B, then generate the images from Part C, and paste the slide content from Part A. You'll have a polished 16-slide deck in a couple of hours.

</div>
