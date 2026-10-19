# FTHR Clips - Elgato Stream Deck Plugin & Local API Integration (v2.0)

Detta paket innehåller den officiella Stream Deck-integrationen och dokumentation för FTHR-Clips lokala Remote API, uppdaterad för **FTHR Clips v2.0**.

---

## 1. Funktioner i v2.0

Med detta plugin kan du direkt på din Stream Deck:
* **Save Replay Clip (med Custom Durations & Property Inspector):**
  * Spara ett buffrat klipp med ett klick.
  * **Nyhet i v2.0:** Stöd för anpassade klipplängder per knapp! I Stream Deck-inställningarna (Property Inspector) kan du välja standard (från FTHR-inställningarna) eller en specifik längd (t.ex. 15s, 30s, 60s, 2m, 5m eller valfria sekunder).
  * Knappen visar automatiskt sin konfigurerade längd (t.ex. `CLIP 60s` eller `CLIP 2m`).
  * **Partiella replay-sparningar (v2.0):** När ett klipp sparas visas den faktiska sparade längden direkt på displayen (`SAVED! 15s`).
* **Toggle Manual Recording:**
  * Starta och stoppa manuell inspelning. Knappen växlar till en glödande röd inspelningsikon med en **realtidstimer** (`REC 01:23`).
* **Screenshot:**
  * Ta omedelbar skärmdump av det aktiva spelet eller skrivbordet med bekräftelsebock.
* **Engine Status:**
  * Visar status i realtid – om FTHR-Clips är anslutet, vilket spel som fångas eller om ett nytt spel har detekterats.
* **Accept Game Detection (Nyhet i v2.0):**
  * När FTHR Clips automatiskt upptäcker ett nytt spel i förgrunden kan du bekräfta byte av capture target med ett tryck utan att behöva tabba ut ur spelet.
* **Dismiss Game Detection (Nyhet i v2.0):**
  * Avfärda popup-notisen om speldetektering direkt från Stream Deck.
* **Toggle Microphone Mute (Nyhet i v2.0):**
  * Muta och avmuta mikrofoninspelningen med visuell realtidsindikator (`MIC LIVE` i cyan eller `MIC MUTED` i gult).

---

## 2. Installation på Stream Deck

### Enkel 1-stegs installation (Windows):

Kör det medföljande PowerShell-skriptet `install_streamdeck_plugin.ps1`:
```powershell
.\integrations\streamdeck\install_streamdeck_plugin.ps1
```
Skriptet kopierar automatiskt filerna till `%APPDATA%\Elgato\StreamDeck\Plugins\` och startar om Stream Deck-appen vid behov.

---

## 3. Hur arkitekturen fungerar

Stream Deck-pluginet kommunicerar via ett lokalt WebSocket- och REST-gränssnitt på `ws://127.0.0.1:19840/api/v1/ws`.

```text
Stream Deck Button Press ──> plugin.js (WebEngine) ──[WebSocket]──> FTHR-Clips RemoteApiController
                                                                            │ (Qt Queued Signal)
                                                                            ▼
                                                                    MainWindow / C++ Engine
```

### Fördelar:
1. **Noll externa beroenden:** Pluginet körs med Stream Decks inbyggda runtime utan externa npm-moduler.
2. **Kopplat från interna backend-ändringar:** Stabil `/api/v1`-kontrakt och WebSocket-händelser.
3. **Resurssnålt:** Ingen polling på disk. Servern läser O(1) atomär status ur minnet.
4. **Auto-Reconnect:** Återansluter automatiskt inom 2 sekunder om FTHR Clips startas om.
