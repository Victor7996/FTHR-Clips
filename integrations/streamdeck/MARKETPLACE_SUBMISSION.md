# Elgato Marketplace Submission Guide for FTHR Clips

This document contains everything needed to publish the **FTHR Clips Stream Deck Plugin** on the [Elgato Maker Console](https://maker.elgato.com).

---

## 1. Package File & Asset Locations

- **Plugin Binary (`.streamDeckPlugin`)**:  
  `H:\desktop\fthr-clips\FTHR-Clips\integrations\streamdeck\com.fthrclips.streamdeck.streamDeckPlugin`
- **Product Icon (512x512 PNG)**:  
  `H:\desktop\fthr-clips\FTHR-Clips\integrations\streamdeck\marketplace_icon.png`

---

## 2. Store Listing Information (Copy-Paste Ready)

### Product Details
- **Product Name**: `FTHR Clips`
- **Subtitle / Short Description**:  
  `Control FTHR Clips v2.0 directly from Stream Deck. Save replay clips, toggle recording, mute mic, and manage game detection. Support on Ko-fi: https://ko-fi.com/victor7996`
- **Category**: `Gaming` (or `Video`)
- **Tags**: `fthr`, `clips`, `replay`, `recording`, `gaming`, `capture`, `stream`
- **Website / Support URL**:  
  `https://ko-fi.com/victor7996`

---

### Detailed Description (Markdown for Marketplace)

```markdown
# FTHR Clips for Stream Deck

Take full tactile control over **FTHR Clips** directly from your Elgato Stream Deck. Save instant replay buffer clips, start and stop manual recording with live timers, accept foreground game switches, mute your microphone, and monitor capture engine status in real time.

---

### Key Features

- **Instant Replay Clips**: Save highlights from your rolling replay buffer with dynamic duration feedback (`CLIP 30s`, `CLIP 60s`, etc.) that automatically reflects your active FTHR Clips settings. Shows instant visual confirmation when saving is completed (`SAVING...` -> `SAVED!`).
- **Manual Recording with Live Timers**: Start and stop recordings on the fly. The button dynamically transitions to an active red recording state displaying a live elapsed timer (`REC 01:23`).
- **Microphone Mute Toggle**: Instantly mute and unmute your microphone with live visual state indicators (`MIC LIVE` -> `MIC MUTED`).
- **Game Detection Accept & Dismiss**: Prompted foreground game detection right on your keys — accept capture switching to a newly detected game with one tap or dismiss it.
- **Screenshot Capture**: Take clean desktop and game screenshots with a single tap.
- **Real-Time Engine Status**: Displays your current capture status, active game title, and capture engine health directly on your Stream Deck canvas.

---

### Prerequisites

1. **FTHR Clips** (Windows or Linux) installed and running.
2. Stream Deck & Remote API enabled in FTHR Clips (*Settings -> General -> System*, enabled by default on port `19840`).

---

### Support the Project

If you love FTHR Clips and this Stream Deck plugin, consider supporting development on **Ko-fi**:
[https://ko-fi.com/victor7996](https://ko-fi.com/victor7996)

---

### Open Source

FTHR Clips is an open-source, hardware-accelerated clipping and recording software designed for gamers and content creators. Visit our [GitHub Repository](https://github.com/Victor7996/fthr-clips-streamdeck) for documentation, source code, and community support.
```

---

### Release Notes (v1.0.0.0)

```markdown
Initial release of the official FTHR Clips Stream Deck integration:
- Save Clip action with dynamic clip buffer duration display
- Toggle Manual Recording action with live elapsed timer
- Quick Screenshot capture action
- Engine Status monitor action
- Zero external dependencies: powered by the high-performance local WebSocket & REST API
```

---

## 3. How to Submit on Maker Console

1. Navigate to [https://maker.elgato.com](https://maker.elgato.com) and log in with your Elgato account.
2. Click **Create Product** -> Select **Plugin**.
3. Drag and drop the packaged file:  
   `com.fthrclips.streamdeck.streamDeckPlugin`
4. Upload the icon:  
   `marketplace_icon.png`
5. Paste the product description, subtitle, and release notes from section 2 above.
6. Select the category (**Gaming** / **Video**).
7. Click **Submit for Review**. Elgato's review team typically approves submissions within 2-5 business days.
