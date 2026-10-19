# FTHR Clips - Elgato Stream Deck Plugin & Local API Integration (v2.0)

[![Support on Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20the%20Project-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/victor7996)
[![Elgato SDK](https://img.shields.io/badge/Elgato%20SDK-v3-blue?style=for-the-badge)](https://maker.elgato.com)
[![Stream Deck](https://img.shields.io/badge/Stream%20Deck-6.9%2B-green?style=for-the-badge)](https://www.elgato.com/stream-deck)

Official Elgato Stream Deck integration for **FTHR Clips v2.0**. Control replay clip saving, manual recording with live timers, game detection prompts, microphone muting, and engine status directly from your Stream Deck keys.

☕ **Support development on Ko-fi:** [https://ko-fi.com/victor7996](https://ko-fi.com/victor7996)

---

## 1. Features in v2.0

* **⚡ Save Replay Clip:**
  * Save a highlight from your rolling replay buffer with a single press, using the settings configured in FTHR Clips.
  * Dynamically displays the app's active clip buffer duration in real time (e.g., `CLIP 30s` or `CLIP 60s`).
  * **Partial Replay Save Feedback:** When a clip is saved, the button displays the exact saved duration (`SAVED! 15s`).
* **🔴 Toggle Manual Recording:**
  * Start and stop manual recording on the fly. The button dynamically transitions to an active red recording state displaying a live elapsed timer (`REC 01:23`).
* **🎙️ Microphone Mute Toggle (New in v2.0):**
  * Mute and unmute microphone recording with live visual feedback (`MIC LIVE` in cyan, `MIC MUTED` in amber).
* **🎮 Game Detection Accept & Dismiss (New in v2.0):**
  * When FTHR Clips prompts for a newly detected foreground game, accept capture switching or dismiss the alert with one tap without alt-tabbing.
* **📸 Screenshot Capture:**
  * Instantly take and save a screenshot of the active game or desktop with visual confirmation.
* **🛡️ Real-Time Engine Status:**
  * Monitors capture status, active game title, and engine health in real time.

---

## 2. Installation

### Option A: Install via Release Package (`.streamDeckPlugin`)
Double-click `com.fthrclips.streamdeck.streamDeckPlugin` or open it with the Elgato Stream Deck desktop application to install automatically.

### Option B: Local Developer Script (Windows)
Run the included PowerShell installer script:
```powershell
.\install_streamdeck_plugin.ps1
```
The script deploys the plugin directly to `%APPDATA%\Elgato\StreamDeck\Plugins\` and restarts Stream Deck.

---

## 3. Architecture & How It Works

The Stream Deck plugin communicates with FTHR Clips over a local loopback WebSocket and REST API at `ws://127.0.0.1:19840/api/v1/ws` and `http://127.0.0.1:19840/api/v1`.

```text
Stream Deck Button Press ──> plugin.js (WebEngine) ──[WebSocket]──> FTHR Clips RemoteApiController
                                                                            │ (Qt Queued Signal)
                                                                            ▼
                                                                    MainWindow / C++ Engine
```

### Highlights:
1. **Zero External Dependencies:** Runs in Stream Deck's native WebEngine runtime without requiring third-party runtime bundles.
2. **Synchronized with App Settings:** All parameters (durations, audio levels, hotkeys) are configured inside FTHR Clips settings and automatically reflected on the keys.
3. **Decoupled Contract:** Uses a stable `/api/v1/` REST and RFC 6455 WebSocket interface.
4. **Auto-Reconnect:** Automatically detects connection loss and reconnects within 2 seconds when FTHR Clips launches or restarts.

---

## 4. Building & Packaging

To validate and package the plugin using the official Elgato CLI:
```bash
npx -y @elgato/cli validate com.fthrclips.streamdeck.sdPlugin
npx -y @elgato/cli pack com.fthrclips.streamdeck.sdPlugin -o ./ -f
```

---

## 5. License

GPL-3.0-only. Part of the [FTHR Clips](https://github.com/FTHR-Community/FTHR-Clips) project.
