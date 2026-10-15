# FTHR Clips - Elgato Stream Deck Plugin & Local API Integration

Detta paket innehåller den officiella Stream Deck-integrationen och dokumentation för FTHR-Clips lokala Remote API.

---

## 1. Funktioner

Med detta plugin kan du direkt på din Stream Deck:
* **Save Replay Clip:** Spara ett buffrat klipp med ett klick. Visar aktuell buffertlängd (t.ex. `CLIP 30s`) och blinkar med en grön bock samt *"SAVED!"* när klippet är skrivet till disk.
* **Toggle Manual Recording:** Starta och stoppa manuell inspelning. Knappen växlar till en glödande röd inspelningsikon med en **realtidstimer** (`REC 01:23`).
* **Screenshot:** Ta omedelbar skärmdump av spelet eller skrivbordet med bekräftelse.
* **Engine Status:** Visar status i realtid – om FTHR-Clips är anslutet och namnet på det aktiva spelet som fångas.

---

## 2. Installation på Stream Deck

### Enkel 1-stegs installation (Windows):

Kopiera plugin-mappen `com.fthrclips.streamdeck.sdPlugin` till Elgatos Stream Deck plugin-katalog:

Kör följande i PowerShell:
```powershell
$target = "$env:APPDATA\Elgato\StreamDeck\Plugins\com.fthrclips.streamdeck.sdPlugin"
Copy-Item -Recurse -Force "H:\desktop\fthr-clips\FTHR-Clips\integrations\streamdeck\com.fthrclips.streamdeck.sdPlugin" $target
```

Starta därefter om Stream Deck-appen (eller dra ur och sätt i din Stream Deck).  
Nu dyker kategorin **FTHR Clips** upp i din Stream Deck-meny till höger, och du kan dra ut knapparna direkt på displayen!

---

## 3. Hur arkitekturen fungerar

Stream Deck-pluginet kommunicerar via ett lokalt WebSocket-gränssnitt på `ws://127.0.0.1:19840/api/v1/ws`.

```text
Stream Deck Button Press ──> plugin.js (Node.js) ──[WebSocket]──> FTHR-Clips RemoteApiController
                                                                          │ (Qt Queued Signal)
                                                                          ▼
                                                                  MainWindow / C++ Engine
```

### Fördelar:
1. **Noll externa beroenden:** Pluginet körs med Stream Decks inbyggda Node.js-motor utan externa `npm install`-krav.
2. **Kopplat från interna backend-ändringar:** Om FTHR-Clips byter C++ capture engine eller minnesstruktur förblir detta API-kontrakt identiskt.
3. **Resurssnålt:** Ingen polling på hårddisken. Servern läser O(1) atomär status ur RAM.
4. **Auto-Reconnect:** Om FTHR-Clips startas om återansluter pluginen automatiskt inom 2 sekunder.
