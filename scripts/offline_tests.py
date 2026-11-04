"""Pytest plugin: disallow outbound connections and production service ports."""
import socket
from contextvars import ContextVar

_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_socketpair = socket.socketpair
_making_socketpair = ContextVar("making_test_socketpair", default=False)
PRODUCTION_PORTS = {8888, 8009, *range(8011, 8026)}


def check(address):
    if isinstance(address, tuple):
        host, port = address[:2]
        if host not in {"127.0.0.1", "::1", "localhost"} or (port in PRODUCTION_PORTS and not _making_socketpair.get()):
            raise RuntimeError(f"Offline test blocked network access to {host}:{port}")


def connect(self, address):
    check(address)
    return _connect(self, address)


def connect_ex(self, address):
    check(address)
    return _connect_ex(self, address)


def socketpair(*args, **kwargs):
    # Windows asyncio's own socketpair can receive a reserved-number ephemeral
    # port. It creates both endpoints itself; it cannot target a live service.
    token = _making_socketpair.set(True)
    try:
        return _socketpair(*args, **kwargs)
    finally:
        _making_socketpair.reset(token)


def pytest_configure(config):
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.socketpair = socketpair


def pytest_unconfigure(config):
    socket.socket.connect = _connect
    socket.socket.connect_ex = _connect_ex
    socket.socketpair = _socketpair
