"""Local Remote API Server for FTHR-Clips.

Provides a decoupled HTTP REST and RFC 6455 WebSocket interface on 127.0.0.1
for hardware controllers (Elgato Stream Deck), OBS dock overlays, and macros.

Architectural guarantees:
1. Thread-safe: incoming actions emit Qt queued signals; GUI/engine is never called directly.
2. Decoupled contract: exposes a normalized /api/v1/ schema that remains stable
   regardless of internal C++ engine or UI refactorings.
3. Zero external dependencies: pure Python standard library (socket, threading, json, hashlib).
4. DoS/Rebinding protected: binds only to loopback, validates Host headers, and rate-limits commands.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import select
import socket
import struct
import sys
import threading
import time
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QObject, Signal, Slot


API_VERSION = '2.0.0'
DEFAULT_PORT = 19840
DEFAULT_HOST = '127.0.0.1'
WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
RATE_LIMIT_ACTIONS_INTERVAL = 0.5  # Seconds between destructive actions (e.g. save_clip)


class WebSocketFrameParser:
    """Minimal RFC 6455 WebSocket frame encoder and decoder."""

    @staticmethod
    def create_handshake_response(sec_key: str) -> bytes:
        accept_raw = sec_key.strip() + WS_GUID
        accept_hash = hashlib.sha1(accept_raw.encode('utf-8')).digest()
        accept_b64 = base64.b64encode(accept_hash).decode('utf-8')
        response = (
            'HTTP/1.1 101 Switching Protocols\r\n'
            'Upgrade: websocket\r\n'
            'Connection: Upgrade\r\n'
            f'Sec-WebSocket-Accept: {accept_b64}\r\n'
            '\r\n'
        )
        return response.encode('utf-8')

    @staticmethod
    def encode_text_frame(message: str) -> bytes:
        data = message.encode('utf-8')
        length = len(data)
        header = bytearray()
        # Fin bit set (0x80) + opcode text (0x01)
        header.append(0x81)

        if length <= 125:
            header.append(length)
        elif length <= 65535:
            header.append(126)
            header.extend(struct.pack('!H', length))
        else:
            header.append(127)
            header.extend(struct.pack('!Q', length))

        return bytes(header) + data

    @staticmethod
    def decode_frame(raw_data: bytes) -> tuple[int, bytes, int] | None:
        """Decode a single WebSocket frame.

        Returns (opcode, payload, total_bytes_consumed) or None if frame is incomplete.
        """
        if len(raw_data) < 2:
            return None

        byte1 = raw_data[0]
        byte2 = raw_data[1]

        opcode = byte1 & 0x0F
        masked = bool(byte2 & 0x80)
        payload_len = byte2 & 0x7F

        offset = 2
        if payload_len == 126:
            if len(raw_data) < 4:
                return None
            payload_len = struct.unpack('!H', raw_data[2:4])[0]
            offset = 4
        elif payload_len == 127:
            if len(raw_data) < 10:
                return None
            payload_len = struct.unpack('!Q', raw_data[2:10])[0]
            offset = 10

        mask_key = None
        if masked:
            if len(raw_data) < offset + 4:
                return None
            mask_key = raw_data[offset:offset + 4]
            offset += 4

        if len(raw_data) < offset + payload_len:
            return None

        payload = bytearray(raw_data[offset:offset + payload_len])
        if masked and mask_key:
            for i in range(payload_len):
                payload[i] ^= mask_key[i % 4]

        total_consumed = offset + payload_len
        return opcode, bytes(payload), total_consumed


class RemoteApiController(QObject):
    """Qt-bridged API server managing HTTP REST and WebSocket connections."""

    # Outgoing signals to Qt Main Thread
    request_save_clip = Signal(int)       # duration in seconds (0 = use configured default)
    request_toggle_recording = Signal()
    request_start_recording = Signal()
    request_stop_recording = Signal()
    request_screenshot = Signal()
    request_confirm_game_detection = Signal()
    request_dismiss_game_detection = Signal()
    request_toggle_mic = Signal()

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, parent: QObject | None = None):
        super().__init__(parent)
        self.host = host
        self.port = port

        # Normalized atomic state snapshot
        self._state_lock = threading.Lock()
        self._state: dict[str, Any] = {
            'api_version': API_VERSION,
            'engine_connected': False,
            'state': 'idle',                     # idle, recording, saving_clip, error
            'is_recording': False,
            'recording_elapsed_seconds': 0.0,
            'recording_elapsed_formatted': '00:00:00',
            'clip_buffer_seconds': 30,
            'can_clip': True,
            'can_record': True,
            'active_game': '',
            'pending_game': '',
            'active_codec': '',
            'fps': 60,
            'resolution': '',
            'mic_muted': False,
            'last_saved_clip': '',
        }

        # Rate limiter timestamps
        self._rate_limits: dict[str, float] = {}

        # Sockets and workers
        self._server_sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._clients: set[socket.socket] = set()
        self._clients_lock = threading.Lock()
        self._client_buffers: dict[socket.socket, bytearray] = {}
        self._is_websocket: dict[socket.socket, bool] = {}

    # State update methods called by Qt thread

    @Slot(dict)
    def update_state(self, updates: dict[str, Any]) -> None:
        """Update the state snapshot and broadcast changes if state transitioned."""
        with self._state_lock:
            old_state = self._state.get('state')
            self._state.update(updates)
            new_state = self._state.get('state')
            current_snapshot = dict(self._state)

        if old_state != new_state:
            self.broadcast_event('state_changed', current_snapshot)

    def get_state(self) -> dict[str, Any]:
        """Atomically read the current normalized status snapshot."""
        with self._state_lock:
            return dict(self._state)

    # Event broadcasting to connected WebSockets

    def broadcast_event(self, event_name: str, data: dict[str, Any] | None = None) -> None:
        """Push an RFC 6455 text frame to all connected WebSocket clients."""
        payload = json.dumps({
            'event': event_name,
            'timestamp': time.time(),
            'data': data or {},
        })
        frame = WebSocketFrameParser.encode_text_frame(payload)

        with self._clients_lock:
            dead_clients: list[socket.socket] = []
            for client in list(self._clients):
                if not self._is_websocket.get(client, False):
                    continue
                try:
                    client.sendall(frame)
                except OSError:
                    dead_clients.append(client)

            for dead in dead_clients:
                self._remove_client(dead)

    def notify_clip_save_started(self, duration: int = 0) -> None:
        with self._state_lock:
            self._state['state'] = 'saving_clip'
        self.broadcast_event('clip_save_started', {'duration': duration})

    def notify_clip_saved(self, path: str, duration: int = 0) -> None:
        with self._state_lock:
            self._state['state'] = 'recording' if self._state.get('is_recording') else 'idle'
            self._state['last_saved_clip'] = path
        self.broadcast_event('clip_saved', {
            'path': path,
            'filename': os.path.basename(path),
            'duration': duration,
        })

    def notify_clip_save_failed(self, error: str) -> None:
        with self._state_lock:
            self._state['state'] = 'recording' if self._state.get('is_recording') else 'idle'
        self.broadcast_event('clip_save_failed', {'error': error})

    def notify_recording_started(self, path: str = '') -> None:
        with self._state_lock:
            self._state['state'] = 'recording'
            self._state['is_recording'] = True
            self._state['recording_elapsed_seconds'] = 0.0
            self._state['recording_elapsed_formatted'] = '00:00:00'
        self.broadcast_event('recording_started', {'path': path})

    def notify_recording_stopped(self, path: str = '') -> None:
        with self._state_lock:
            self._state['state'] = 'idle'
            self._state['is_recording'] = False
        self.broadcast_event('recording_stopped', {'path': path})

    def notify_recording_tick(self, elapsed_seconds: float, formatted: str) -> None:
        with self._state_lock:
            self._state['recording_elapsed_seconds'] = elapsed_seconds
            self._state['recording_elapsed_formatted'] = formatted
        self.broadcast_event('recording_tick', {
            'elapsed_seconds': elapsed_seconds,
            'formatted': formatted,
        })

    def notify_game_detected(self, game_title: str) -> None:
        with self._state_lock:
            self._state['pending_game'] = game_title
        self.broadcast_event('game_detected', {'game': game_title})

    def notify_game_cleared(self) -> None:
        with self._state_lock:
            self._state['pending_game'] = ''
        self.broadcast_event('game_cleared', {})

    def notify_mic_toggled(self, is_muted: bool) -> None:
        with self._state_lock:
            self._state['mic_muted'] = bool(is_muted)
        self.broadcast_event('mic_toggled', {'muted': bool(is_muted)})

    # Rate limiting guard

    def _check_rate_limit(self, action_name: str) -> bool:
        now = time.monotonic()
        last = self._rate_limits.get(action_name, 0.0)
        if now - last < RATE_LIMIT_ACTIONS_INTERVAL:
            return False
        self._rate_limits[action_name] = now
        return True

    # Server lifecycle

    def start(self) -> bool:
        """Start the remote API server in a dedicated daemon thread."""
        if self._running:
            return True

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen(16)
            sock.setblocking(False)
            self._server_sock = sock
        except OSError as exc:
            print(f'[RemoteAPI] Failed to bind {self.host}:{self.port} - {exc}')
            return False

        self._running = True
        self._thread = threading.Thread(
            target=self._server_loop,
            daemon=True,
            name='fthr-remote-api',
        )
        self._thread.start()
        print(f'[RemoteAPI] Listening on http://{self.host}:{self.port}/api/v1')
        return True

    def stop(self) -> None:
        """Gracefully stop the server and disconnect all clients."""
        if not self._running:
            return

        self._running = False
        with self._clients_lock:
            for client in list(self._clients):
                try:
                    # Send WebSocket Close Frame if applicable (1000 Normal Closure)
                    if self._is_websocket.get(client, False):
                        close_frame = bytearray([0x88, 0x02, 0x03, 0xE8])
                        client.sendall(close_frame)
                    client.shutdown(socket.SHUT_RDWR)
                    client.close()
                except OSError:
                    pass
            self._clients.clear()
            self._client_buffers.clear()
            self._is_websocket.clear()

        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None

        print('[RemoteAPI] Server stopped.')

    # Main network select loop

    def _server_loop(self) -> None:
        assert self._server_sock is not None
        while self._running:
            try:
                rlist = [self._server_sock]
                with self._clients_lock:
                    rlist.extend(list(self._clients))

                readable, _, exceptional = select.select(rlist, [], rlist, 0.25)
            except (OSError, ValueError):
                break

            for sock in exceptional:
                if sock is self._server_sock:
                    continue
                self._remove_client(sock)

            for sock in readable:
                if sock is self._server_sock:
                    self._accept_connection()
                else:
                    self._handle_client_data(sock)

    def _accept_connection(self) -> None:
        if not self._server_sock:
            return
        try:
            client, addr = self._server_sock.accept()
            client.setblocking(False)
            with self._clients_lock:
                self._clients.add(client)
                self._client_buffers[client] = bytearray()
                self._is_websocket[client] = False
        except OSError:
            pass

    def _remove_client(self, client: socket.socket) -> None:
        with self._clients_lock:
            self._clients.discard(client)
            self._client_buffers.pop(client, None)
            self._is_websocket.pop(client, None)
        try:
            client.close()
        except OSError:
            pass

    def _handle_client_data(self, client: socket.socket) -> None:
        try:
            chunk = client.recv(4096)
            if not chunk:
                self._remove_client(client)
                return
        except OSError:
            self._remove_client(client)
            return

        with self._clients_lock:
            buf = self._client_buffers.get(client)
            if buf is None:
                return
            buf.extend(chunk)
            is_ws = self._is_websocket.get(client, False)

        if not is_ws:
            # Process HTTP request or WebSocket handshake
            if b'\r\n\r\n' in buf:
                self._process_http_request(client, buf)
        else:
            # Process WebSocket frames
            self._process_websocket_frames(client, buf)

    # HTTP request dispatching

    def _process_http_request(self, client: socket.socket, buf: bytearray) -> None:
        header_end = buf.find(b'\r\n\r\n')
        raw_headers = bytes(buf[:header_end]).decode('utf-8', errors='replace')
        lines = raw_headers.split('\r\n')
        if not lines:
            self._remove_client(client)
            return

        request_line = lines[0].split()
        if len(request_line) < 2:
            self._remove_client(client)
            return

        method = request_line[0].upper()
        raw_path = request_line[1]

        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.strip().lower()] = v.strip()

        # Host security check to protect against DNS rebinding attacks
        host_header = headers.get('host', '').split(':')[0]
        if host_header not in ('127.0.0.1', 'localhost', '::1'):
            self._send_http_response(client, 403, {'error': 'Forbidden host header'}, keep_alive=False)
            self._remove_client(client)
            return

        # Check for WebSocket Upgrade
        if headers.get('upgrade', '').lower() == 'websocket':
            sec_key = headers.get('sec-websocket-key')
            if sec_key:
                resp = WebSocketFrameParser.create_handshake_response(sec_key)
                try:
                    client.sendall(resp)
                    with self._clients_lock:
                        self._is_websocket[client] = True
                        del buf[:header_end + 4]
                    # Immediately push initial state upon successful handshake
                    self._push_initial_state_to_client(client)
                    return
                except OSError:
                    self._remove_client(client)
                    return

        # Regular REST HTTP request
        content_length = int(headers.get('content-length', 0))
        body_start = header_end + 4
        if len(buf) < body_start + content_length:
            # Wait for rest of payload
            return

        body = bytes(buf[body_start:body_start + content_length])
        del buf[:body_start + content_length]

        self._route_rest_request(client, method, raw_path, headers, body)

    def _push_initial_state_to_client(self, client: socket.socket) -> None:
        state = self.get_state()
        payload = json.dumps({
            'event': 'initial_state',
            'timestamp': time.time(),
            'data': state,
        })
        frame = WebSocketFrameParser.encode_text_frame(payload)
        try:
            client.sendall(frame)
        except OSError:
            self._remove_client(client)

    def _route_rest_request(
            self,
            client: socket.socket,
            method: str,
            raw_path: str,
            headers: dict[str, str],
            body: bytes) -> None:
        parsed = urlparse(raw_path)
        path = parsed.path.rstrip('/')

        # Handle CORS preflight
        if method == 'OPTIONS':
            self._send_cors_response(client)
            return

        # Parse JSON body if present
        body_json: dict[str, Any] = {}
        if body:
            try:
                body_json = json.loads(body.decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                self._send_http_response(client, 400, {'ok': False, 'error': 'Invalid JSON body'})
                return

        # REST Endpoints
        if method == 'GET' and path in ('/api/v1/status', '/api/v1'):
            self._send_http_response(client, 200, self.get_state())

        elif method == 'POST' and path == '/api/v1/actions/save_clip':
            if not self._check_rate_limit('save_clip'):
                self._send_http_response(client, 429, {
                    'ok': False,
                    'error': 'rate_limited',
                    'message': 'Please wait before saving another clip.',
                })
                return
            duration = int(body_json.get('duration_seconds') or body_json.get('duration') or 0)
            self.request_save_clip.emit(duration)
            self.notify_clip_save_started(duration)
            self._send_http_response(client, 200, {
                'ok': True,
                'action': 'save_clip',
                'duration_seconds': duration,
                'message': 'Clip save requested.',
            })

        elif method == 'POST' and path in ('/api/v1/actions/record/toggle', '/api/v1/actions/record_toggle'):
            self.request_toggle_recording.emit()
            self._send_http_response(client, 200, {
                'ok': True,
                'action': 'toggle_recording',
            })

        elif method == 'POST' and path == '/api/v1/actions/record/start':
            self.request_start_recording.emit()
            self._send_http_response(client, 200, {
                'ok': True,
                'action': 'start_recording',
            })

        elif method == 'POST' and path == '/api/v1/actions/record/stop':
            self.request_stop_recording.emit()
            self._send_http_response(client, 200, {
                'ok': True,
                'action': 'stop_recording',
            })

        elif method == 'POST' and path == '/api/v1/actions/screenshot':
            self.request_screenshot.emit()
            self._send_http_response(client, 200, {
                'ok': True,
                'action': 'screenshot',
            })

        elif method == 'POST' and path in ('/api/v1/actions/game/confirm', '/api/v1/actions/confirm_game'):
            self.request_confirm_game_detection.emit()
            self._send_http_response(client, 200, {
                'ok': True,
                'action': 'confirm_game_detection',
            })

        elif method == 'POST' and path in ('/api/v1/actions/game/dismiss', '/api/v1/actions/dismiss_game'):
            self.request_dismiss_game_detection.emit()
            self._send_http_response(client, 200, {
                'ok': True,
                'action': 'dismiss_game_detection',
            })

        elif method == 'POST' and path in ('/api/v1/actions/mic/toggle', '/api/v1/actions/toggle_mic'):
            self.request_toggle_mic.emit()
            self._send_http_response(client, 200, {
                'ok': True,
                'action': 'toggle_mic',
            })

        else:
            self._send_http_response(client, 404, {'ok': False, 'error': 'Not found'})

    def _send_cors_response(self, client: socket.socket) -> None:
        headers = (
            'HTTP/1.1 204 No Content\r\n'
            'Access-Control-Allow-Origin: *\r\n'
            'Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n'
            'Access-Control-Allow-Headers: Content-Type, Authorization\r\n'
            'Content-Length: 0\r\n'
            'Connection: keep-alive\r\n'
            '\r\n'
        )
        try:
            client.sendall(headers.encode('utf-8'))
        except OSError:
            self._remove_client(client)

    def _send_http_response(
            self,
            client: socket.socket,
            status_code: int,
            payload: dict[str, Any],
            keep_alive: bool = True) -> None:
        body = json.dumps(payload, indent=2).encode('utf-8')
        reason = {200: 'OK', 400: 'Bad Request', 403: 'Forbidden', 404: 'Not Found', 429: 'Too Many Requests'}.get(
            status_code, 'Unknown')
        conn_header = 'keep-alive' if keep_alive else 'close'
        headers = (
            f'HTTP/1.1 {status_code} {reason}\r\n'
            'Content-Type: application/json; charset=utf-8\r\n'
            'Access-Control-Allow-Origin: *\r\n'
            f'Content-Length: {len(body)}\r\n'
            f'Connection: {conn_header}\r\n'
            '\r\n'
        )
        try:
            client.sendall(headers.encode('utf-8') + body)
            if not keep_alive:
                self._remove_client(client)
        except OSError:
            self._remove_client(client)

    # WebSocket frame processing

    def _process_websocket_frames(self, client: socket.socket, buf: bytearray) -> None:
        while True:
            decoded = WebSocketFrameParser.decode_frame(bytes(buf))
            if decoded is None:
                break
            opcode, payload, consumed = decoded
            del buf[:consumed]

            if opcode == 0x8:  # Close frame
                self._remove_client(client)
                return
            elif opcode == 0x9:  # Ping frame -> reply with Pong (0xA)
                pong = bytearray([0x8A, len(payload)]) + payload
                try:
                    client.sendall(bytes(pong))
                except OSError:
                    self._remove_client(client)
                    return
            elif opcode == 0x1:  # Text frame (command)
                self._handle_ws_command(client, payload)

    def _handle_ws_command(self, client: socket.socket, payload: bytes) -> None:
        try:
            msg = json.loads(payload.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return

        action = str(msg.get('action') or msg.get('command') or '').lower()
        duration_val = msg.get('duration_seconds') or msg.get('duration') or 0
        if action == 'save_clip':
            if not self._check_rate_limit('save_clip'):
                resp = WebSocketFrameParser.encode_text_frame(json.dumps({
                    'event': 'error',
                    'message': 'Please wait before saving another clip.',
                }))
                try:
                    client.sendall(resp)
                except OSError:
                    self._remove_client(client)
                return
            duration = int(duration_val)
            self.request_save_clip.emit(duration)
            self.notify_clip_save_started(duration)
        elif action in ('toggle_recording', 'toggle_record'):
            self.request_toggle_recording.emit()
        elif action in ('start_recording', 'start_record'):
            self.request_start_recording.emit()
        elif action in ('stop_recording', 'stop_record'):
            self.request_stop_recording.emit()
        elif action in ('screenshot', 'save_screenshot'):
            self.request_screenshot.emit()
        elif action in ('confirm_game_detection', 'confirm_game', 'accept_game'):
            self.request_confirm_game_detection.emit()
        elif action in ('dismiss_game_detection', 'dismiss_game'):
            self.request_dismiss_game_detection.emit()
        elif action in ('toggle_mic', 'mute_mic', 'mic_toggle'):
            self.request_toggle_mic.emit()
        elif action in ('status', 'get_status'):
            self._push_initial_state_to_client(client)
