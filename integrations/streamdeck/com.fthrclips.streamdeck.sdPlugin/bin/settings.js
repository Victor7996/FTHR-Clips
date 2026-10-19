/**
 * FTHR Clips - Elgato Stream Deck Official Plugin Settings
 * 
 * Centralized configuration for the Stream Deck integration and Local Remote API.
 * Follows the project standards defined across repository documentation:
 * - Single source of truth for API, WebSocket, action UUIDs, and UI defaults.
 * - Zero external runtime dependencies.
 * - Universal module support (WebEngine browser runtime, Node.js CLI, Property Inspector).
 * 
 * SPDX-License-Identifier: GPL-3.0-only
 */

(function (root, factory) {
    if (typeof module !== 'undefined' && module.exports) {
        // Node.js runtime / CLI
        module.exports = factory();
    } else {
        // WebEngine / Browser / Property Inspector
        root.FTHR_SETTINGS = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    const API = {
        HOST: '127.0.0.1',
        PORT: 19840,
        VERSION: '2.0.0',
        get BASE_URL() {
            return `http://${this.HOST}:${this.PORT}`;
        },
        get WS_URL() {
            return `ws://${this.HOST}:${this.PORT}/api/v1/ws`;
        },
        ENDPOINTS: {
            STATUS: '/api/v1/status',
            SAVE_CLIP: '/api/v1/actions/save_clip',
            RECORD_TOGGLE: '/api/v1/actions/record/toggle',
            RECORD_START: '/api/v1/actions/record/start',
            RECORD_STOP: '/api/v1/actions/record/stop',
            SCREENSHOT: '/api/v1/actions/screenshot',
            GAME_CONFIRM: '/api/v1/actions/game/confirm',
            GAME_DISMISS: '/api/v1/actions/game/dismiss',
            MIC_TOGGLE: '/api/v1/actions/mic/toggle'
        },
        RECONNECT_INTERVAL_MS: 2000,
        REQUEST_TIMEOUT_MS: 3000
    };

    const ACTIONS = {
        UUID_PREFIX: 'com.fthrclips.streamdeck',
        CLIP: 'com.fthrclips.streamdeck.clip',
        RECORD: 'com.fthrclips.streamdeck.record',
        SCREENSHOT: 'com.fthrclips.streamdeck.screenshot',
        STATUS: 'com.fthrclips.streamdeck.status',
        GAME_CONFIRM: 'com.fthrclips.streamdeck.game_confirm',
        GAME_DISMISS: 'com.fthrclips.streamdeck.game_dismiss',
        MIC: 'com.fthrclips.streamdeck.mic'
    };

    const CLIPS = {
        DEFAULT_BUFFER_SECONDS: 30,
        STANDARD_DURATIONS: [0, 15, 30, 45, 60, 120, 300, 600, 900, 1800],
        MAX_CUSTOM_DURATION_SECONDS: 1800,
        SAVED_FEEDBACK_MS: 2500,
        FAILED_FEEDBACK_MS: 2500
    };

    const UI = {
        TITLES: {
            OFFLINE: 'OFFLINE',
            FTHR_OFFLINE: 'FTHR\nOFFLINE',
            RECORD_IDLE: 'RECORD',
            SAVING: 'SAVING…',
            SAVED: 'SAVED!',
            FAILED: 'FAILED',
            CAPTURE_READY: 'CAPTURE\nREADY',
            GAME_READY: 'GAME\nREADY',
            GAME_IDLE: 'DISMISS\nIDLE',
            ACCEPT_PREFIX: 'ACCEPT\n',
            DISMISS_PREFIX: 'DISMISS\n',
            MIC_LIVE: 'MIC\nLIVE',
            MIC_MUTED: 'MIC\nMUTED',
            MIC_OFFLINE: 'MIC\nOFFLINE'
        },
        MAX_GAME_TITLE_CHARS: 10,
        MAX_PROMPT_GAME_CHARS: 7
    };

    return Object.freeze({
        API: Object.freeze(API),
        ACTIONS: Object.freeze(ACTIONS),
        CLIPS: Object.freeze(CLIPS),
        UI: Object.freeze(UI)
    });
}));
