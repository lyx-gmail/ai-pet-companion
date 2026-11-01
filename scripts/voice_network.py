"""Validate an explicit local voice bind; never change networking or start services."""
import ipaddress
import re
import socket


def device_allowed(headers, config):
    """Identity filter only; the WebSocket must still verify its HMAC token."""
    auth = config.get('server', {}).get('auth', {})
    expected = config.get('Memory', {}).get('PetMemory', {}).get('expected_device_id', '')
    normalized = {key.lower(): value for key, value in headers.items()}
    return bool(auth.get('enabled') is True and not auth.get('allowed_devices')
                and expected and normalized.get('device-id', '').lower() == expected.lower()
                and normalized.get('client-id', '').strip())


def network_config(bind_ip='127.0.0.1', device_id=''):
    try:
        address = ipaddress.IPv4Address(bind_ip)
    except ipaddress.AddressValueError:
        raise ValueError('Use an explicit IPv4 address') from None
    device_id = device_id.strip().lower()
    if device_id and not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', device_id):
        raise ValueError('Device ID must be a colon-separated MAC address')
    if address != ipaddress.IPv4Address('127.0.0.1'):
        ranges = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')
        if not any(address in ipaddress.IPv4Network(cidr) for cidr in ranges):
            raise ValueError('LAN bind must use an explicit RFC1918 IPv4 address')
        if not device_id:
            raise ValueError('LAN mode requires the verified device ID')
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind((str(address), 0))
        except OSError:
            raise ValueError('Bind address is not available locally') from None
    return {'ip': str(address), 'expected_device_id': device_id,
            'websocket': f'ws://{address}:8000/xiaozhi/v1/',
            'vision_explain': f'http://{address}:8003/mcp/vision/explain'}
