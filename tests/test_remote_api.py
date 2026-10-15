"""Comprehensive test suite for FTHR-Clips Local Remote API and WebSocket."""

import base64
import json
import socket
import struct
import time
import urllib.error
import urllib.request
import pytest
from PySide6.QtCore import QCoreApplication

from core.remote_api import RemoteApiController, WebSocketFrameParser


@pytest.fixture
def qt_app():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


@pytest.fixture
def api_server(qt_app):
    # Use ephemeral/free port
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()

    server = RemoteApiController(host='127.0.0.1', port=port)
    assert server.start() is True
    time.sleep(0.05)
    try:
        yield server
    finally:
        server.stop()


def test_status_endpoint(api_server):
    url = f'http://127.0.0.1:{api_server.port}/api/v1/status'
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode('utf-8'))
        assert data['api_version'] == '1.0.0'
        assert data['state'] == 'idle'
        assert data['can_clip'] is True
        assert data['can_record'] is True


def test_host_header_rebinding_protection(api_server):
    url = f'http://127.0.0.1:{api_server.port}/api/v1/status'
    req = urllib.request.Request(url, headers={'Host': 'evil-site.com'})
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 403


def test_action_signals(api_server, qt_app):
    signal_results = {}

    def on_save_clip(duration):
        signal_results['save_clip'] = duration

    def on_toggle():
        signal_results['toggle'] = True

    api_server.request_save_clip.connect(on_save_clip)
    api_server.request_toggle_recording.connect(on_toggle)

    # 1. Save clip action
    url = f'http://127.0.0.1:{api_server.port}/api/v1/actions/save_clip'
    req = urllib.request.Request(
        url,
        data=json.dumps({'duration_seconds': 45}).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        res = json.loads(resp.read().decode('utf-8'))
        assert res['ok'] is True

    # 2. Toggle record action
    url = f'http://127.0.0.1:{api_server.port}/api/v1/actions/record/toggle'
    req = urllib.request.Request(url, data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200

    # Process Qt events so QueuedConnection signals are dispatched to slots
    for _ in range(10):
        qt_app.processEvents()
        if signal_results.get('save_clip') is not None and signal_results.get('toggle') is not None:
            break
        time.sleep(0.02)
    assert signal_results.get('save_clip') == 45
    assert signal_results.get('toggle') is True


def test_save_clip_rate_limiting(api_server):
    url = f'http://127.0.0.1:{api_server.port}/api/v1/actions/save_clip'
    req1 = urllib.request.Request(url, data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req1) as resp1:
        assert resp1.status == 200

    # Immediate second call should be throttled
    req2 = urllib.request.Request(url, data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req2)
    assert exc_info.value.code == 429


def test_websocket_handshake_and_events(api_server, qt_app):
    # Connect raw client socket to test RFC 6455 WebSocket implementation
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', api_server.port))
    sock.settimeout(2.0)

    # 1. Send Handshake
    sec_key = base64.b64encode(b'0123456789abcdef').decode('utf-8')
    handshake = (
        f'GET /api/v1/ws HTTP/1.1\r\n'
        f'Host: 127.0.0.1:{api_server.port}\r\n'
        'Upgrade: websocket\r\n'
        'Connection: Upgrade\r\n'
        f'Sec-WebSocket-Key: {sec_key}\r\n'
        'Sec-WebSocket-Version: 13\r\n'
        '\r\n'
    )
    sock.sendall(handshake.encode('utf-8'))

    # Read Handshake Response
    raw_resp = sock.recv(4096)
    assert b'101 Switching Protocols' in raw_resp
    assert b'Sec-WebSocket-Accept:' in raw_resp

    header_end = raw_resp.find(b'\r\n\r\n')
    remaining = raw_resp[header_end + 4:] if header_end != -1 else b''
    if not remaining:
        remaining = sock.recv(4096)

    # 2. Read initial status frame pushed by server
    decoded = WebSocketFrameParser.decode_frame(remaining)
    assert decoded is not None
    opcode, payload, _ = decoded
    assert opcode == 1  # Text frame
    initial_state = json.loads(payload.decode('utf-8'))
    assert initial_state['event'] == 'initial_state'
    assert initial_state['data']['state'] == 'idle'

    # 3. Test Broadcast Event (Clip saved)
    api_server.notify_clip_saved('C:/Clips/clip1.mp4', 30)
    raw_frame = sock.recv(4096)
    decoded = WebSocketFrameParser.decode_frame(raw_frame)
    assert decoded is not None
    opcode, payload, _ = decoded
    event_data = json.loads(payload.decode('utf-8'))
    assert event_data['event'] == 'clip_saved'
    assert event_data['data']['filename'] == 'clip1.mp4'

    # 4. Test Client Command to Server (Masked frame per RFC 6455)
    signal_called = []
    api_server.request_toggle_recording.connect(lambda: signal_called.append(True))

    cmd_payload = json.dumps({'command': 'toggle_record'}).encode('utf-8')
    # Client mask key
    mask = b'\x12\x34\x56\x78'
    masked_payload = bytearray(len(cmd_payload))
    for i in range(len(cmd_payload)):
        masked_payload[i] = cmd_payload[i] ^ mask[i % 4]

    # Fin + text opcode (0x81), Masked (0x80) + len
    frame = bytearray([0x81, 0x80 | len(cmd_payload)]) + mask + masked_payload
    sock.sendall(frame)

    for _ in range(10):
        qt_app.processEvents()
        if signal_called:
            break
        time.sleep(0.02)
    assert len(signal_called) == 1

    sock.close()


def test_start_stop_screenshot_and_not_found(api_server, qt_app):
    events = []
    api_server.request_start_recording.connect(lambda: events.append('start'))
    api_server.request_stop_recording.connect(lambda: events.append('stop'))
    api_server.request_screenshot.connect(lambda: events.append('screenshot'))

    # POST start
    url = f'http://127.0.0.1:{api_server.port}/api/v1/actions/record/start'
    req = urllib.request.Request(url, data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200

    # POST stop
    url = f'http://127.0.0.1:{api_server.port}/api/v1/actions/record/stop'
    req = urllib.request.Request(url, data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200

    # POST screenshot
    url = f'http://127.0.0.1:{api_server.port}/api/v1/actions/screenshot'
    req = urllib.request.Request(url, data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200

    for _ in range(10):
        qt_app.processEvents()
        if len(events) == 3:
            break
        time.sleep(0.02)
    assert events == ['start', 'stop', 'screenshot']

    # 404 test
    url = f'http://127.0.0.1:{api_server.port}/api/v1/actions/unknown'
    req = urllib.request.Request(url, data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 404


def test_websocket_ping_pong(api_server):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', api_server.port))
    sock.settimeout(2.0)

    sec_key = base64.b64encode(b'pingpongkey12345').decode('utf-8')
    handshake = (
        f'GET /api/v1/ws HTTP/1.1\r\n'
        f'Host: 127.0.0.1:{api_server.port}\r\n'
        'Upgrade: websocket\r\n'
        'Connection: Upgrade\r\n'
        f'Sec-WebSocket-Key: {sec_key}\r\n'
        'Sec-WebSocket-Version: 13\r\n'
        '\r\n'
    )
    sock.sendall(handshake.encode('utf-8'))
    raw_resp = sock.recv(4096)
    assert b'101 Switching Protocols' in raw_resp
    assert b'Sec-WebSocket-Accept:' in raw_resp

    # If the initial status frame was bundled in the same recv, or comes next, read it
    header_end = raw_resp.find(b'\r\n\r\n')
    remaining = raw_resp[header_end + 4:] if header_end != -1 else b''
    if not remaining:
        remaining = sock.recv(4096)

    # Send Ping frame (0x89) masked
    ping_payload = b'hello-ping'
    mask = b'\xaa\xbb\xcc\xdd'
    masked = bytearray(len(ping_payload))
    for i in range(len(ping_payload)):
        masked[i] = ping_payload[i] ^ mask[i % 4]
    frame = bytearray([0x89, 0x80 | len(ping_payload)]) + mask + masked
    sock.sendall(frame)

    # Receive Pong frame (0x8A)
    pong_raw = sock.recv(1024)
    decoded = WebSocketFrameParser.decode_frame(pong_raw)
    assert decoded is not None
    opcode, payload, _ = decoded
    assert opcode == 0x0A  # Pong
    assert payload == ping_payload

    sock.close()

