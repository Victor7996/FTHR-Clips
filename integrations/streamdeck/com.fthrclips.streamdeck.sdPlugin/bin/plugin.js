/**
 * FTHR Clips - Elgato Stream Deck Official Integration Plugin
 * 
 * Communicates with FTHR-Clips Local API on ws://127.0.0.1:19840/api/v1/ws.
 * Zero external npm dependencies (uses standard Node.js runtime provided by Stream Deck).
 */

const http = require('http');

// Parse Stream Deck CLI arguments
let streamDeckPort = null;
let pluginUUID = null;
let registerEvent = null;

const args = process.argv.slice(2);
for (let i = 0; i < args.length; i++) {
    if (args[i] === '-port') streamDeckPort = args[++i];
    else if (args[i] === '-pluginUUID') pluginUUID = args[++i];
    else if (args[i] === '-registerEvent') registerEvent = args[++i];
}

if (!streamDeckPort || !pluginUUID || !registerEvent) {
    console.error('[FTHR StreamDeck] Missing required CLI arguments from Stream Deck');
    process.exit(1);
}

// Track active visible action contexts
const activeActions = {
    clip: new Set(),
    record: new Set(),
    screenshot: new Set(),
    status: new Set()
};

// Stream Deck WebSocket Connection
let streamDeckWs = null;

// FTHR-Clips State & Connection
let fthrWs = null;
let fthrConnected = false;
let fthrState = {
    is_recording: false,
    recording_elapsed_formatted: '00:00:00',
    clip_buffer_seconds: 30,
    active_game: '',
    state: 'idle'
};

function connectToStreamDeck() {
    const WebSocket = global.WebSocket || require('ws');
    streamDeckWs = new WebSocket(`ws://127.0.0.1:${streamDeckPort}`);

    streamDeckWs.onopen = () => {
        console.log('[FTHR StreamDeck] Connected to Stream Deck software');
        streamDeckWs.send(JSON.stringify({
            event: registerEvent,
            uuid: pluginUUID
        }));
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
        process.exit(0);
    };
}

function handleStreamDeckMessage(msg) {
    const event = msg.event;
    const action = msg.action;
    const context = msg.context;

    if (event === 'willAppear') {
        if (action.endsWith('.clip')) activeActions.clip.add(context);
        else if (action.endsWith('.record')) activeActions.record.add(context);
        else if (action.endsWith('.screenshot')) activeActions.screenshot.add(context);
        else if (action.endsWith('.status')) activeActions.status.add(context);
        syncActionUI(context, action);
    } else if (event === 'willDisappear') {
        if (action.endsWith('.clip')) activeActions.clip.delete(context);
        else if (action.endsWith('.record')) activeActions.record.delete(context);
        else if (action.endsWith('.screenshot')) activeActions.screenshot.delete(context);
        else if (action.endsWith('.status')) activeActions.status.delete(context);
    } else if (event === 'keyDown') {
        handleButtonPress(action, context);
    }
}

function handleButtonPress(action, context) {
    if (!fthrConnected) {
        sendToStreamDeck({
            event: 'showAlert',
            context: context
        });
        sendPostAction('/api/v1/status', {}); // Ping HTTP fallback
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
    }
}

// Stream Deck Helper
function sendToStreamDeck(payload) {
    if (streamDeckWs && streamDeckWs.readyState === 1) {
        streamDeckWs.send(JSON.stringify(payload));
    }
}

function syncAllActions() {
    activeActions.clip.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.clip'));
    activeActions.record.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.record'));
    activeActions.status.forEach(ctx => syncActionUI(ctx, 'com.fthrclips.streamdeck.status'));
}

function syncActionUI(context, action) {
    if (!fthrConnected) {
        if (action.endsWith('.record')) {
            sendToStreamDeck({
                event: 'setState',
                context: context,
                payload: { state: 0 }
            });
            sendToStreamDeck({
                event: 'setTitle',
                context: context,
                payload: { title: 'FTHR\nOFFLINE', target: 0 }
            });
        } else if (action.endsWith('.status')) {
            sendToStreamDeck({
                event: 'setTitle',
                context: context,
                payload: { title: 'OFFLINE', target: 0 }
            });
        }
        return;
    }

    if (action.endsWith('.record')) {
        if (fthrState.is_recording) {
            sendToStreamDeck({
                event: 'setState',
                context: context,
                payload: { state: 1 }
            });
            sendToStreamDeck({
                event: 'setTitle',
                context: context,
                payload: { title: `REC\n${fthrState.recording_elapsed_formatted.slice(3)}`, target: 0 }
            });
        } else {
            sendToStreamDeck({
                event: 'setState',
                context: context,
                payload: { state: 0 }
            });
            sendToStreamDeck({
                event: 'setTitle',
                context: context,
                payload: { title: 'RECORD', target: 0 }
            });
        }
    } else if (action.endsWith('.clip')) {
        const sec = fthrState.clip_buffer_seconds || 30;
        sendToStreamDeck({
            event: 'setTitle',
            context: context,
            payload: { title: `CLIP\n${sec}s`, target: 0 }
        });
    } else if (action.endsWith('.status')) {
        const title = fthrState.active_game ? fthrState.active_game.slice(0, 10) : 'CAPTURE\nREADY';
        sendToStreamDeck({
            event: 'setTitle',
            context: context,
            payload: { title: title, target: 0 }
        });
    }
}

// FTHR-Clips WebSocket Client
function connectToFTHR() {
    const WebSocket = global.WebSocket || require('ws');
    try {
        fthrWs = new WebSocket('ws://127.0.0.1:19840/api/v1/ws');

        fthrWs.onopen = () => {
            console.log('[FTHR StreamDeck] Connected to FTHR-Clips Local API');
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
            fthrWs.close();
        };

        fthrWs.onclose = () => {
            if (fthrConnected) {
                console.log('[FTHR StreamDeck] Disconnected from FTHR-Clips');
            }
            fthrConnected = false;
            syncAllActions();
            setTimeout(connectToFTHR, 2000); // Auto-reconnect every 2 seconds
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
        activeActions.clip.forEach(ctx => {
            sendToStreamDeck({ event: 'showOk', context: ctx });
            sendToStreamDeck({
                event: 'setTitle',
                context: ctx,
                payload: { title: 'SAVED!', target: 0 }
            });
        });
        setTimeout(() => syncActionUI(null, 'com.fthrclips.streamdeck.clip'), 2000);
    } else if (event === 'clip_save_failed') {
        activeActions.clip.forEach(ctx => {
            sendToStreamDeck({ event: 'showAlert', context: ctx });
            sendToStreamDeck({
                event: 'setTitle',
                context: ctx,
                payload: { title: 'FAILED', target: 0 }
            });
        });
        setTimeout(() => syncActionUI(null, 'com.fthrclips.streamdeck.clip'), 2500);
    }
}

function sendFthrCommand(actionName) {
    if (fthrWs && fthrWs.readyState === 1) {
        fthrWs.send(JSON.stringify({ action: actionName }));
    } else {
        // HTTP REST fallback
        sendPostAction(`/api/v1/actions/${actionName === 'save_clip' ? 'save_clip' : 'record/toggle'}`, {});
    }
}

function sendPostAction(endpoint, body) {
    const postData = JSON.stringify(body);
    const options = {
        hostname: '127.0.0.1',
        port: 19840,
        path: endpoint,
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(postData),
            'Host': '127.0.0.1:19840'
        }
    };
    const req = http.request(options, (res) => {});
    req.on('error', () => {});
    req.write(postData);
    req.end();
}

// Start Stream Deck Client and FTHR-Clips Client
connectToStreamDeck();
connectToFTHR();
