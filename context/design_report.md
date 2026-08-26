# AERIS UI/UX Design Report: Mission Command Center

This document outlines the visual identity, user experience philosophy, and structural wireframe for the AERIS (Agentic Earth Reasoning & Intelligence System) frontend, specifically focusing on the **Mission Command Center**.

The goal is to create an interface that is undeniably premium, highly professional, and instantly recognizable as a state-of-the-art intelligence platform. It must avoid looking like a generic web app or a simple chat wrapper.

---

## 1. Aesthetic Direction & Color Scheme

Drawing inspiration from top-tier geospatial and intelligence platforms (Palantir Foundry, Planet Labs, Maxar), the UI will employ a **"Data-Dense Dark Mode"** or "Common Operating Picture" (COP) aesthetic. 

The color scheme is designed to reduce eye strain during prolonged analysis while allowing critical satellite data and AI insights to pop.

### Color Palette

*   **Primary Background (Space Black):** `#0A0D14` (Deep charcoal/navy, avoiding pure `#000000` to maintain depth).
*   **Surface / Panel Backgrounds (Obsidian):** `#141824` with varying levels of opacity (glassmorphism) and subtle border strokes (`#2A3143`).
*   **Primary Accent (AERIS Teal):** `#00E5FF` (Used for primary actions, active states, and glowing data points).
*   **Secondary Accent (Intelligence Blue):** `#3B82F6` (Used for AI chat bubbles, processing states, and secondary highlights).
*   **Alert/Warning (Phosphor Orange/Red):** `#F59E0B` (Warnings, low confidence) and `#EF4444` (Critical alerts, change detection highlights).
*   **Typography (Starlight White):** `#F3F4F6` for primary text, `#9CA3AF` for secondary/metadata.

### Typography & Styling

*   **Primary Font:** `Inter` or `Geist` for exceptional readability in UI elements and chat.
*   **Monospace Font:** `JetBrains Mono` or `Fira Code` for coordinates, execution traces, data tables, and model metrics to give a professional, technical "Bloomberg Terminal" feel.
*   **Styling:** Sharp corners with very slight rounding (e.g., `rounded-md`), thin borders, heavy use of drop shadows to create depth (layering panels over the map).

---

## 2. The "Wow" Factors (Extra Enhancements)

To elevate AERIS beyond the initial idea and secure that "winner" reaction, we will implement these unmentioned "Wow" factors:

> [!TIP]
> **1. Cinematic 3D Transitions (CesiumJS + deck.gl)**
> Instead of abruptly switching pages, transitioning from the Mission Command Center (3D globe view) to the Investigation Workspace should feature a smooth, cinematic camera "fly-to" animation down to the exact Area of Interest (AOI).
>
> **Engine decision (2026-08-26):** CesiumJS owns the Earth — globe, terrain, imagery tiles, camera and fly-to. deck.gl owns the analytical overlays — animated temporal transitions, aggregation, large vector sets — rendered above Cesium and camera-synced. All computation (band math, reprojection, tiling, inference) happens in the backend; the frontend renders and creates the experience. The goal is to make change *felt*, not to build another Google Maps.

> [!TIP]
> **2. Ambient Data Streams (Idle State)**
> When the user is idle on the Mission Command Center, the 3D Earth shouldn't just be static. It should show subtle, glowing ambient data streams—perhaps showing live satellite trajectories (mocked or real), recent global event blips, or a slow, cinematic rotation.

> [!TIP]
> **3. Typewriter & "Decrypting" Text Effects**
> When the AI generates an execution trace or streams an answer, use a very fast, subtle "typewriter" or "terminal decrypt" text effect before the final text settles. This reinforces the "agentic execution" feel.

> [!TIP]
> **4. Glassmorphism with Backdrop Blur**
> UI panels hovering over the 3D map won't be solid blocks. They will use `backdrop-filter: blur()` (glassmorphism) so the user never feels disconnected from the geospatial context underneath. 

> [!TIP]
> **5. Audio Feedback (Subtle)**
> Extremely subtle, premium UI sounds for critical actions: a soft click when a model is selected, a low hum when AI is processing, a satisfying chime when a high-confidence answer is returned. (Can be toggled off).

---

## 3. Mission Command Center: Wireframe & Layout

The Mission Command Center is the entry point. It must balance a sense of global scale with immediate access to powerful tools.

### Conceptual Mockup

Here is a generated vision of the intended aesthetic:

![AERIS Mission Command UI](/absolute/path/to/image/placeholder/aeris_mission_command_ui_1787715405737.png)
*(Note: Replace with the actual generated image path `aeris_mission_command_ui_1787715405737.png`)*
![AERIS Mission Command UI](/C:/Users/Mobil/.gemini/antigravity-ide/brain/1f9f0d81-eb3a-4487-8eb3-002a9e080cc0/aeris_mission_command_ui_1787715405737.png)


### Structural Layout (Grid System)

The layout is a full-screen, non-scrolling dashboard. The 3D Earth acts as the background canvas, with UI panels floating on top.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ █ AERIS Logo             [Global Search / Coordinate Entry]    User | Alerts│
├───────────────┬─────────────────────────────────────────────┬───────────────┤
│               │                                             │               │
│ [LEFT PANEL]  │                                             │ [RIGHT PANEL] │
│ DATA &        │               [CENTER CANVAS]               │ AERIS         │
│ MISSIONS      │                                             │ ASSISTANT     │
│               │               Interactive 3D Earth          │               │
│ - Upload Area │               (CesiumJS)                    │ - Welcome Msg │
│   (Drag/Drop) │               - Shows glowing markers for   │ - Chat Input  │
│               │                 active/past missions        │   (Text/Voice)│
│ - Recent      │                                             │ - Execution   │
│   Imagery     │                                             │   Trace Logs  │
│               │               [Floating Controls]           │ - Suggested   │
│ - Active      │               (Zoom, Compass, Layers)       │   Queries     │
│   Missions    │                                             │               │
│               │                                             │               │
│ - Model Status│                                             │ [MIC] [SEND]  │
└───────────────┴─────────────────────────────────────────────┴───────────────┘
```

### Component Breakdown

#### 1. The Global Header (Top Bar)
*   **Left:** Sleek, minimalist AERIS logo.
*   **Center:** A universal command bar (like Spotlight on Mac). Users can type coordinates, place names, or quick commands (e.g., `/monitor Mumbai`).
*   **Right:** Live system status readout (model fleet health).

> [!NOTE]
> **Removed 2026-08-26:** this slot previously specified a notification bell for completed background
> analyses. Continuous monitoring and alerting are later-tier scope in the source PDF and are not being
> built, so the bell and its `/api/v1/notifications` endpoint were deleted rather than left as a
> non-functional affordance. `AppShell` retains a `headerActionsSlot` extension point for when a later
> surface needs this corner.

#### 2. The Center Canvas (3D Earth)
*   The primary visual anchor. We will use CesiumJS configured with a high-res, dark-themed satellite basemap.
*   The globe will display glowing nodes representing available datasets, recent uploads, or saved mission areas.

#### 3. Left Panel (Data & Context)
*   **Upload Zone:** A prominent, dashed-border drop zone for GeoTIFFs/images. Uses a subtle glowing pulse on drag-over.
*   **Data Catalog:** An accordion list of recently uploaded scenes, showing metadata chips (e.g., `[Optical]`, `[Cloud: 5%]`, `[T0]`).
*   **Mission Library:** Quick access to saved "Monitoring Missions" or past "Investigations".

#### 4. Right Panel (Agentic Interface)
*   This is not a generic chat box. It's a "Command Terminal".
*   **Greeting:** "AERIS online. Global systems nominal. What would you like to investigate?"
*   **Message Bubbles:** User messages are simple. AI responses are structured cards.
*   **Execution Trace UI:** When AERIS is working, this panel shows a collapsible, step-by-step loading state (e.g., `> Inspecting Metadata... [Done]`, `> Routing to ChangeFormer... [Processing]`).
*   **Input Area:** A large, multi-line input field. A prominent microphone icon for the Voice Command feature. 

---

## Next Steps for Phase 1 Development

If you approve this design direction, Phase 1 execution will begin with:
1.  Setting up the Next.js layout structure matching this wireframe.
2.  Configuring the Tailwind theme with the specified exact color tokens and typography.
3.  Building the foundational UI components (Panels, Inputs, Chat Bubbles) in the `components/sharedUI` folder.
4.  Integrating the base 3D Earth viewer (CesiumJS) in the center canvas, with deck.gl reserved for the analytical overlay layers in the Investigation Workspace.
