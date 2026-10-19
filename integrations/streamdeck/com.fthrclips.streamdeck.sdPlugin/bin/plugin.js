/**
 * FTHR Clips - Elgato Stream Deck Official Integration Plugin (v2.0)
 * 
 * Runs in Stream Deck's internal runtime via index.html (or standalone Node.js).
 * Communicates with FTHR Clips Local API on ws://127.0.0.1:19840/api/v1/ws.
 * 
 * v2.0 Additions:
 * - Custom per-action clip durations (15s, 30s, 60s, 2m, 5m, custom) with Property Inspector support.
 * - Partial replay save actual duration reporting (SAVED! Xs).
 * - Game detection Accept/Dismiss actions for automatic foreground game detection.
 * - Microphone mute/unmute status tracking and controls.
 */

// Connection parameters
let streamDeckPort = null;
let pluginUUID = null;
let registerEvent = null;
let streamDeckWs = null;

// Track active visible action contexts
const activeActions = {
    clip: new Set(),
    record: new Set(),
    screenshot: new Set(),
    status: new Set(),
    game_confirm: new Set(),
    game_dismiss: new Set(),
    mic: new Set()
};


// FTHR Clips state snapshot
let fthrWs = null;
let fthrConnected = false;
let fthrState = {
    is_recording: false,
    recording_elapsed_formatted: '00:00:00',
    clip_buffer_seconds: 30,
    active_game: '',
    pending_game: '',
    mic_muted: false,
    state: 'idle'
};

/**
 * Standard Stream Deck connection entrypoint called by Stream Deck software
 */
function connectElgatoStreamDeckSocket(port, uuid, eventType, appInfoString, actionInfoString) {
    streamDeckPort = port;
    pluginUUID = uuid;
    registerEvent = eventType;
    connectToStreamDeck();
    connectToFTHR();
}

// Attach to window if in browser/webview environment
if (typeof window !== 'undefined') {
    window.connectElgatoStreamDeckSocket = connectElgatoStreamDeckSocket;
}

// Fallback for CLI/Node environment if executed standalone
if (typeof process !== 'undefined' && process.argv && process.argv.length > 2) {
    const args = process.argv.slice(2);
    for (let i = 0; i < args.length; i++) {
        if (args[i] === '-port') streamDeckPort = args[++i];
        else if (args[i] === '-pluginUUID') pluginUUID = args[++i];
        else if (args[i] === '-registerEvent') registerEvent = args[++i];
    }
    if (streamDeckPort && pluginUUID && registerEvent) {
        connectToStreamDeck();
        connectToFTHR();
    }
}

function connectToStreamDeck() {
    if (!streamDeckPort) return;
    const WSClass = (typeof WebSocket !== 'undefined') ? WebSocket : (typeof global !== 'undefined' && global.WebSocket ? global.WebSocket : require('ws'));
    try {
        streamDeckWs = new WSClass(`ws://127.0.0.1:${streamDeckPort}`);

        streamDeckWs.onopen = () => {
            console.log('[FTHR StreamDeck] Connected to Stream Deck software');
            streamDeckWs.send(JSON.stringify({
                event: registerEvent,
                uuid: pluginUUID
            }));
            syncAllActions();
        };

        streamDeckWs.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                handleStreamDeckMessage(msg);
            } catch (err) {
                console.error('[FTHR StreamDeck] Failed parsing SD message:', err);
            }
        };

        streamDeckWs.onclose = () => {
            console.log('[FTHR StreamDeck] Stream Deck connection closed');
        };
    } catch (e) {
        console.error('[FTHR StreamDeck] Stream Deck connect error:', e);
    }
}

function handleStreamDeckMessage(msg) {
    const event = msg.event;
    const action = msg.action;
    const context = msg.context;

    if (event === 'willAppear') {
        registerActionContext(action, context);
        syncActionUI(context, action);
    } else if (event === 'willDisappear') {
        unregisterActionContext(action, context);
    } else if (event === 'keyDown') {
        handleButtonPress(action, context);
    }
}

function registerActionContext(action, context) {
    if (!action) return;
    if (action.endsWith('.clip')) activeActions.clip.add(context);
    else if (action.endsWith('.record')) activeActions.record.add(context);
    else if (action.endsWith('.screenshot')) activeActions.screenshot.add(context);
    else if (action.endsWith('.status')) activeActions.status.add(context);
    else if (action.endsWith('.game_confirm')) activeActions.game_confirm.add(context);
    else if (action.endsWith('.game_dismiss')) activeActions.game_dismiss.add(context);
    else if (action.endsWith('.mic')) activeActions.mic.add(context);
}

function unregisterActionContext(action, context) {
    if (!action) return;
    if (action.endsWith('.clip')) activeActions.clip.delete(context);
    else if (action.endsWith('.record')) activeActions.record.delete(context);
    else if (action.endsWith('.screenshot')) activeActions.screenshot.delete(context);
    else if (action.endsWith('.status')) activeActions.status.delete(context);
    else if (action.endsWith('.game_confirm')) activeActions.game_confirm.delete(context);
    else if (action.endsWith('.game_dismiss')) activeActions.game_dismiss.delete(context);
    else if (action.endsWith('.mic')) activeActions.mic.delete(context);
}

function handleButtonPress(action, context) {
    if (!fthrConnected) {
        sendToStreamDeck({
            event: 'showAlert',
            context: context
        });
        sendPostAction('/api/v1/status', {});
        return;
    }

    if (action.endsWith('.clip')) {
        sendFthrCommand('save_clip');
        sendToStreamDeck({
            event: 'setTitle',
            context: context,
            payload: { title: 'SAVING…', target: 0 }
        });
    } else if (action.endsWith('.record')) {
        sendFthrCommand('toggle_record');
    } else if (action.endsWith('.screenshot')) {
        sendFthrCommand('screenshot');
        sendToStreamDeck({
            event: 'showOk',
            context: context
        });
    } else if (action.endsWith('.status')) {
        sendFthrCommand('get_status');
    } else if (action.endsWith('.game_confirm')) {
        sendFthrCommand('confirm_game_detection');
        sendToStreamDeck({ event: 'showOk', context: context });
    } else if (action.endsWith('.game_dismiss')) {
        sendFthrCommand('dismiss_game_detection');
        sendToStreamDeck({ event: 'showOk', context: context });
    } else if (action.endsWith('.mic')) {
        sendFthrCommand('toggle_mic');
    }
}

function sendToStreamDeck(payload) {
    if (streamDeckWs && streamDeckWs.readyState === 1) {
        streamDeckWs.send(JSON.stringify(payload));
    }
}

function formatDurationLabel(seconds) {
    if (!seconds || seconds <= 0) return '30s';
    if (seconds < 60) return `${seconds}s`;
    if (seconds % 60 === 0) return `${seconds / 60}m`;
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}m${s}s`;
}

function syncAllActions() {
    activeActions.clip.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.clip'));
    activeActions.record.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.record'));
    activeActions.status.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.status'));
    activeActions.game_confirm.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.game_confirm'));
    activeActions.game_dismiss.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.game_dismiss'));
    activeActions.mic.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.mic'));
}

function syncActionUI(context, action) {
    if (!context || !action) return;

    if (!fthrConnected) {
        if (action.endsWith('.record')) {
            sendToStreamDeck({ event: 'setState', context: context, payload: { state: 0 } });
            sendToStreamDeck({ event: 'setTitle', context: context, payload: { title: 'FTHR\nOFFLINE', target: 0 } });
        } else if (action.endsWith('.clip')) {
            sendToStreamDeck({ event: 'setTitle', context: context, payload: { title: 'CLIP\nOFFLINE', target: 0 } });
        } else if (action.endsWith('.status')) {
            sendToStreamDeck({ event: 'setTitle', context: context, payload: { title: 'OFFLINE', target: 0 } });
        } else if (action.endsWith('.game_confirm')) {
            sendToStreamDeck({ event: 'setTitle', context: context, payload: { title: 'ACCEPT\nOFFLINE', target: 0 } });
        } else if (action.endsWith('.game_dismiss')) {
            sendToStreamDeck({ event: 'setTitle', context: context, payload: { title: 'DISMISS\nOFFLINE', target: 0 } });
        } else if (action.endsWith('.mic')) {
            sendToStreamDeck({ event: 'setState', context: context, payload: { state: 0 } });
            sendToStreamDeck({ event: 'setTitle', context: context, payload: { title: 'MIC\nOFFLINE', target: 0 } });
        }
        return;
    }

    if (action.endsWith('.record')) {
        if (fthrState.is_recording) {
            sendToStreamDeck({ event: 'setState', context: context, payload: { state: 1 } });
            sendToStreamDeck({
                event: 'setTitle',
                context: context,
                payload: { title: `REC\n${fthrState.recording_elapsed_formatted.slice(3)}`, target: 0 }
            });
        } else {
            sendToStreamDeck({ event: 'setState', context: context, payload: { state: 0 } });
            sendToStreamDeck({ event: 'setTitle', context: context, payload: { title: 'RECORD', target: 0 } });
        }
    } else if (action.endsWith('.clip')) {
        const sec = fthrState.clip_buffer_seconds || 30;
        sendToStreamDeck({
            event: 'setTitle',
            context: context,
            payload: { title: `CLIP\n${formatDurationLabel(sec)}`, target: 0 }
        });
    } else if (action.endsWith('.status')) {
        let title = 'CAPTURE\nREADY';
        if (fthrState.pending_game) {
            title = `DETECTED\n${fthrState.pending_game.slice(0, 8)}`;
        } else if (fthrState.active_game) {
            title = fthrState.active_game.slice(0, 10);
        }
        sendToStreamDeck({
            event: 'setTitle',
            context: context,
            payload: { title: title, target: 0 }
        });
    } else if (action.endsWith('.game_confirm')) {
        const game = fthrState.pending_game ? fthrState.pending_game.slice(0, 7) : 'READY';
        sendToStreamDeck({
            event: 'setTitle',
            context: context,
            payload: { title: `ACCEPT\n${game}`, target: 0 }
        });
    } else if (action.endsWith('.game_dismiss')) {
        const game = fthrState.pending_game ? fthrState.pending_game.slice(0, 7) : 'IDLE';
        sendToStreamDeck({
            event: 'setTitle',
            context: context,
            payload: { title: `DISMISS\n${game}`, target: 0 }
        });
    } else if (action.endsWith('.mic')) {
        if (fthrState.mic_muted) {
            sendToStreamDeck({ event: 'setState', context: context, payload: { state: 1 } });
            sendToStreamDeck({ event: 'setTitle', context: context, payload: { title: 'MIC\nMUTED', target: 0 } });
        } else {
            sendToStreamDeck({ event: 'setState', context: context, payload: { state: 0 } });
            sendToStreamDeck({ event: 'setTitle', context: context, payload: { title: 'MIC\nLIVE', target: 0 } });
        }
    }
}

function connectToFTHR() {
    const WSClass = (typeof WebSocket !== 'undefined') ? WebSocket : (typeof global !== 'undefined' && global.WebSocket ? global.WebSocket : require('ws'));
    try {
        fthrWs = new WSClass('ws://127.0.0.1:19840/api/v1/ws');

        fthrWs.onopen = () => {
            console.log('[FTHR StreamDeck] Connected to FTHR Clips Local API v2.0');
            fthrConnected = true;
            syncAllActions();
        };

        fthrWs.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                handleFthrEvent(message);
            } catch (err) {
                console.error('[FTHR StreamDeck] Bad FTHR JSON:', err);
            }
        };

        fthrWs.onerror = () => {
            if (fthrWs && fthrWs.close) fthrWs.close();
        };

        fthrWs.onclose = () => {
            if (fthrConnected) {
                console.log('[FTHR StreamDeck] Disconnected from FTHR Clips');
            }
            fthrConnected = false;
            syncAllActions();
            setTimeout(connectToFTHR, 2000);
        };
    } catch (e) {
        fthrConnected = false;
        setTimeout(connectToFTHR, 2000);
    }
}

function handleFthrEvent(msg) {
    const event = msg.event;
    const data = msg.data || {};

    if (event === 'initial_state' || event === 'state_changed') {
        Object.assign(fthrState, data);
        syncAllActions();
    } else if (event === 'recording_started') {
        fthrState.is_recording = true;
        fthrState.recording_elapsed_formatted = '00:00:00';
        syncAllActions();
    } else if (event === 'recording_stopped') {
        fthrState.is_recording = false;
        syncAllActions();
    } else if (event === 'recording_tick') {
        fthrState.recording_elapsed_formatted = data.formatted || '00:00:00';
        activeActions.record.forEach(ctx => {
            sendToStreamDeck({
                event: 'setTitle',
                context: ctx,
                payload: { title: `REC\n${fthrState.recording_elapsed_formatted.slice(3)}`, target: 0 }
            });
        });
    } else if (event === 'clip_save_started') {
        activeActions.clip.forEach(ctx => {
            sendToStreamDeck({
                event: 'setTitle',
                context: ctx,
                payload: { title: 'SAVING…', target: 0 }
            });
        });
    } else if (event === 'clip_saved') {
        // v2.0: Show actual saved duration (supporting partial replay saves)
        const savedDuration = data.duration ? `${data.duration}s` : 'SAVED!';
        const feedbackTitle = data.duration ? `SAVED!\n${savedDuration}` : 'SAVED!';
        activeActions.clip.forEach(ctx => {
            sendToStreamDeck({ event: 'showOk', context: ctx });
            sendToStreamDeck({
                event: 'setTitle',
                context: ctx,
                payload: { title: feedbackTitle, target: 0 }
            });
        });
        setTimeout(() => {
            activeActions.clip.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.clip'));
        }, 2500);
    } else if (event === 'clip_save_failed') {
        activeActions.clip.forEach(ctx => {
            sendToStreamDeck({ event: 'showAlert', context: ctx });
            sendToStreamDeck({
                event: 'setTitle',
                context: ctx,
                payload: { title: 'FAILED', target: 0 }
            });
        });
        setTimeout(() => {
            activeActions.clip.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.clip'));
        }, 2500);
    } else if (event === 'game_detected') {
        fthrState.pending_game = data.game || '';
        activeActions.game_confirm.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.game_confirm'));
        activeActions.game_dismiss.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.game_dismiss'));
        activeActions.status.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.status'));
    } else if (event === 'game_cleared') {
        fthrState.pending_game = '';
        activeActions.game_confirm.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.game_confirm'));
        activeActions.game_dismiss.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.game_dismiss'));
        activeActions.status.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.status'));
    } else if (event === 'mic_toggled') {
        fthrState.mic_muted = Boolean(data.muted);
        activeActions.mic.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.mic'));
    }
}

function sendFthrCommand(actionName, data) {
    const payload = Object.assign({ action: actionName }, data || {});
    if (fthrWs && fthrWs.readyState === 1) {
        fthrWs.send(JSON.stringify(payload));
    } else {
        const endpointMap = {
            'save_clip': '/api/v1/actions/save_clip',
            'toggle_record': '/api/v1/actions/record/toggle',
            'screenshot': '/api/v1/actions/screenshot',
            'confirm_game_detection': '/api/v1/actions/game/confirm',
            'dismiss_game_detection': '/api/v1/actions/game/dismiss',
            'toggle_mic': '/api/v1/actions/mic/toggle',
            'get_status': '/api/v1/status'
        };
        const endpoint = endpointMap[actionName] || `/api/v1/actions/${actionName}`;
        sendPostAction(endpoint, payload);
    }
}

function sendPostAction(endpoint, body) {
    if (typeof fetch !== 'undefined') {
        fetch(`http://127.0.0.1:19840${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {})
        }).catch(() => {});
        return;
    }
    try {
        const http = require('http');
        const postData = JSON.stringify(body || {});
        const req = http.request({
            hostname: '127.0.0.1',
            port: 19840,
            path: endpoint,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(postData),
                'Host': '127.0.0.1:19840'
            }
        }, () => {});
        req.on('error', () => {});
        req.write(postData);
        req.end();
    } catch (_) {}
}
