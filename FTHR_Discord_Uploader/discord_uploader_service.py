"""One-shot process boundary for the optional FTHR Discord Webhook Extension."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


PLUGIN_ID = 'com.fthrclips.discord-uploader'
PLUGIN_VERSION = '1.0.0'
TERMS_VERSION = '2026-09-28-v1'
PRIVACY_VERSION = '2026-09-28-v1'

_NETWORK_ACTIONS = {'upload', 'test_connection'}
_MAX_CLIP_BYTES = 25 * 1024 * 1024  # 25 MB default Discord limit (50 MB / 500 MB for boosted servers)
_MAX_BOOSTED_BYTES = 100 * 1024 * 1024
_BOUNDARY = b'----FTHRDiscordUploadBoundary' + hashlib.sha256(str(time.time()).encode()).hexdigest()[:16].encode()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'Invalid JSON object in {path}')
    return value


def _validate_activation(
        receipt_path: Path,
        request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not receipt_path.is_file():
        raise PermissionError('The Discord Webhook Extension has not been installed in FTHR Clips.')
    receipt = _read_object(receipt_path)
    if receipt.get('plugin_id') != PLUGIN_ID:
        raise PermissionError('Activation receipt belongs to a different package.')
    if receipt.get('plugin_version') != PLUGIN_VERSION:
        raise PermissionError('Activation version does not match.')
    if receipt.get('terms_version') != TERMS_VERSION:
        raise PermissionError('Discord Webhook Terms of Service must be accepted again.')
    if receipt.get('privacy_version') != PRIVACY_VERSION:
        raise PermissionError('Discord Webhook Privacy Policy must be accepted again.')
    if request.get('activation_id') != receipt.get('activation_id'):
        raise PermissionError('Discord Webhook activation token is invalid.')

    expected_exe = str(receipt.get('executable_sha256', '')).lower()
    current_exe = Path(sys.executable)
    # PyInstaller frozen binary check; allow python.exe in source/test mode
    if expected_exe and current_exe.name.lower().startswith('fthr discord uploader'):
        if _sha256(current_exe).lower() != expected_exe:
            raise PermissionError('Discord Webhook executable integrity check failed.')

    settings_path = Path(str(receipt.get('settings_file', '')))
    settings = _read_object(settings_path) if settings_path.is_file() else {}
    if (str(request.get('action', '')) in _NETWORK_ACTIONS
            and not bool(settings.get('upload_enabled', False))):
        raise PermissionError('The Discord Webhook Extension is disabled in FTHR Clips.')
    return receipt, settings


def _validate_webhook_url(raw_url: str) -> str:
    url = str(raw_url or '').strip()
    if not url:
        raise ValueError('Enter a Discord Webhook URL first.')
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != 'https' or not parsed.hostname:
        raise ValueError('Discord Webhook URL must use https://.')
    hostname = parsed.hostname.lower()
    if not (hostname == 'discord.com' or hostname.endswith('.discord.com')
            or hostname == 'discordapp.com' or hostname.endswith('.discordapp.com')):
        raise ValueError(f'Invalid Discord webhook hostname ({hostname}). Expected discord.com.')
    return url


def _get_webhook_url(settings: dict[str, Any], request: dict[str, Any]) -> str:
    config = request.get('config') if isinstance(request.get('config'), dict) else {}
    url = str(
        config.get('discord_webhook_url')
        or config.get('discord_active_webhook')
        or settings.get('discord_webhook_url')
        or settings.get('discord_active_webhook')
        or ''
    ).strip()
    if not url:
        webhooks = settings.get('discord_webhooks', [])
        if isinstance(webhooks, list) and webhooks:
            first = webhooks[0]
            if isinstance(first, dict):
                url = str(first.get('url', '')).strip()
            elif isinstance(first, str):
                url = first.strip()
    return _validate_webhook_url(url)


def _multipart_post(
        url: str,
        fields: dict[str, str],
        file_field: str,
        file_path: Path,
        headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != 'https' or not parsed.hostname:
        raise ValueError('Discord Webhook URL must use https://.')

    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            b'--' + _BOUNDARY + b'\r\n'
            + f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode('utf-8')
            + str(value).encode('utf-8') + b'\r\n'
        )

    safe_name = file_path.name.replace('"', '_').replace('\\', '_')
    content_type = mimetypes.guess_type(file_path.name)[0] or 'application/octet-stream'
    file_header = (
        b'--' + _BOUNDARY + b'\r\n'
        + f'Content-Disposition: form-data; name="{file_field}"; filename="{safe_name}"\r\n'.encode('utf-8')
        + f'Content-Type: {content_type}\r\n\r\n'.encode('ascii')
    )
    footer = b'\r\n--' + _BOUNDARY + b'--\r\n'
    content_length = sum(map(len, parts)) + len(file_header) + file_path.stat().st_size + len(footer)

    request_path = parsed.path or '/'
    if parsed.query:
        request_path += '?' + parsed.query

    connection = http.client.HTTPSConnection(parsed.hostname, parsed.port, timeout=120)
    try:
        connection.putrequest('POST', request_path)
        connection.putheader('Content-Type', f'multipart/form-data; boundary={_BOUNDARY.decode("ascii")}')
        connection.putheader('Content-Length', str(content_length))
        connection.putheader('User-Agent', 'FTHR-Clips/Discord-Webhook-Plugin')
        for name, value in (headers or {}).items():
            connection.putheader(name, value)
        connection.endheaders()

        for part in parts:
            connection.send(part)
        connection.send(file_header)
        with file_path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                connection.send(chunk)
        connection.send(footer)

        response = connection.getresponse()
        raw = response.read()
        return response.status, raw
    finally:
        connection.close()


def _action_test_connection(settings: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    url = _get_webhook_url(settings, request)
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'FTHR-Clips/Discord-Webhook-Plugin'},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return {'ok': True, 'message': f'Discord Webhook reachable (HTTP {response.status}).'}
    except urllib.error.HTTPError as exc:
        if exc.code in {200, 204}:
            return {'ok': True, 'message': f'Discord Webhook reachable (HTTP {exc.code}).'}
        return {'ok': False, 'message': f'Discord Webhook returned HTTP {exc.code}.'}
    except Exception as exc:
        return {'ok': False, 'message': f'Could not reach Discord Webhook: {exc}'}


def _action_upload(
        settings: dict[str, Any],
        request: dict[str, Any],
        receipt: dict[str, Any]) -> dict[str, Any]:
    path_str = str(request.get('path', '')).strip()
    if not path_str:
        raise ValueError('No file path provided for upload.')
    file_path = Path(path_str).resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f'File not found: {file_path}')

    size = file_path.stat().st_size
    if size > _MAX_BOOSTED_BYTES:
        raise ValueError(f'File size ({size / (1024*1024):.1f} MB) exceeds maximum allowed upload limit.')

    # Ensure path is within allowed directories
    allowed_roots = request.get('allowed_roots') or []
    if allowed_roots:
        resolved_roots = [Path(r).resolve() for r in allowed_roots]
        is_safe = any(
            str(file_path).startswith(str(r)) for r in resolved_roots
        )
        if not is_safe:
            raise PermissionError('Target file is outside the allowed clip directories.')

    webhook_url = _get_webhook_url(settings, request)
    parsed = urllib.parse.urlparse(webhook_url)
    query = urllib.parse.parse_qs(parsed.query)
    query['wait'] = ['true']
    new_query = urllib.parse.urlencode(query, doseq=True)
    request_url = urllib.parse.urlunparse(parsed._replace(query=new_query))

    payload = json.dumps({'content': f'🎬 New clip: {file_path.name}'})
    fields = {'payload_json': payload}

    status, raw = _multipart_post(request_url, fields, 'file', file_path)
    text = raw.decode('utf-8', errors='replace').strip()
    if not (200 <= status < 300):
        return {'ok': False, 'message': f'Discord returned HTTP {status}: {text[:200]}'}

    response_url = ''
    try:
        data = json.loads(text)
        if (isinstance(data, dict)
                and isinstance(data.get('attachments'), list)
                and data['attachments']):
            response_url = str(data['attachments'][0].get('url') or '').strip()
    except ValueError:
        pass

    result_url = response_url or 'Discord upload complete.'
    entry = {
        'path': str(file_path),
        'provider': 'discord_webhook',
        'url': result_url,
        'raw_url': response_url,
        'size': size,
        'timestamp': time.time(),
        'favorite': False,
    }

    # Record history if history file is provided
    history_path_str = str(request.get('history_file') or receipt.get('history_file') or '')
    if history_path_str:
        try:
            h_path = Path(history_path_str)
            h_path.parent.mkdir(parents=True, exist_ok=True)
            history = json.loads(h_path.read_text(encoding='utf-8')) if h_path.is_file() else {}
            history[str(file_path)] = entry
            temp_h = h_path.with_suffix('.tmp')
            temp_h.write_text(json.dumps(history, indent=2), encoding='utf-8')
            os.replace(str(temp_h), str(h_path))
        except Exception:
            pass

    return {
        'ok': True,
        'url': result_url,
        'raw_url': response_url,
        'message': 'Upload complete.',
        'entry': entry,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activation-receipt', required=True, help='Path to activation.json')
    args = parser.parse_args()

    try:
        raw_input = sys.stdin.read()
        request = json.loads(raw_input) if raw_input.strip() else {}
        if not isinstance(request, dict):
            raise ValueError('Request must be a JSON object.')

        action = str(request.get('action', '')).strip()
        receipt_path = Path(args.activation_receipt)
        receipt, settings = _validate_activation(receipt_path, request)

        if action == 'account_status':
            response = {
                'ok': True,
                'installed': True,
                'plugin_id': PLUGIN_ID,
                'plugin_version': PLUGIN_VERSION,
            }
        elif action == 'test_connection':
            response = _action_test_connection(settings, request)
        elif action == 'upload':
            response = _action_upload(settings, request, receipt)
        else:
            response = {'ok': False, 'message': f'Unsupported action: {action}'}

    except Exception as exc:
        response = {'ok': False, 'message': str(exc)}

    sys.stdout.write(json.dumps(response) + '\n')
    sys.stdout.flush()
    return 0 if response.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
