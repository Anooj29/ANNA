"""Telemetry-link tests: framing, disconnects and reconnection."""

from __future__ import annotations

import json
import socket
import time

import pytest

from anna_robot.telemetry import TelemetryLink


@pytest.fixture
def link():
    link = TelemetryLink(0, host="127.0.0.1", wait_for_client=False)
    yield link
    link.close()


def connect(link) -> socket.socket:
    port = link._server.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port), timeout=2)
    _wait_for(lambda: link.is_connected)
    return client


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_starts_without_waiting_for_a_companion(link):
    assert link.is_connected is False


def test_several_commands_in_one_packet_are_split(link):
    """Two commands in one TCP segment used to become one corrupt string."""
    client = connect(link)
    client.sendall(b"yes buddy\ncheck temperature\n")
    time.sleep(0.1)
    assert link.receive_commands() == ["yes buddy", "check temperature"]
    client.close()


def test_a_split_command_is_reassembled(link):
    client = connect(link)
    client.sendall(b"start\n")          # Establishes that this peer frames lines.
    time.sleep(0.1)
    assert link.receive_commands() == ["start"]
    client.sendall(b"check ")
    time.sleep(0.1)
    assert link.receive_commands() == []  # Incomplete: held, not emitted.
    client.sendall(b"temperature\n")
    time.sleep(0.1)
    assert link.receive_commands() == ["check temperature"]
    client.close()


def test_a_companion_that_sends_no_newline_still_works(link):
    """The original companion app sent bare text with no framing at all."""
    client = connect(link)
    client.sendall(b"yes buddy")
    time.sleep(0.1)
    assert link.receive_commands() == ["yes buddy"]
    client.close()


def test_commands_are_lower_cased_and_stripped(link):
    client = connect(link)
    client.sendall(b"  Hey ANNA  \n")
    time.sleep(0.1)
    assert link.receive_commands() == ["hey anna"]
    client.close()


def test_blank_lines_are_ignored(link):
    client = connect(link)
    client.sendall(b"\n\n  \nstop\n")
    time.sleep(0.1)
    assert link.receive_commands() == ["stop"]
    client.close()


def test_send_delivers_json_lines(link):
    client = connect(link)
    assert link.send({"state": "SEARCH", "distance": 42.0}) is True
    payload = json.loads(client.makefile().readline())
    assert payload["state"] == "SEARCH"
    client.close()


def test_send_without_a_client_is_a_no_op(link):
    assert link.send({"state": "SEARCH"}) is False


def test_unserialisable_payloads_do_not_raise(link):
    connect(link)
    assert link.send({"bad": object()}) is True  # Coerced via default=str.


def test_a_disconnect_is_detected(link):
    """An empty read used to look exactly like 'no command', forever."""
    client = connect(link)
    client.close()
    _wait_for(lambda: link.receive_commands() == [] and not link.is_connected)
    assert link.is_connected is False


def test_a_new_companion_can_reconnect(link):
    first = connect(link)
    first.close()
    _wait_for(lambda: not link.is_connected) or link.receive_commands()
    second = connect(link)
    assert link.is_connected is True
    second.sendall(b"hey anna\n")
    time.sleep(0.1)
    assert link.receive_commands() == ["hey anna"]
    second.close()


def test_receive_command_still_returns_a_single_string(link):
    client = connect(link)
    client.sendall(b"yes buddy\n")
    time.sleep(0.1)
    assert link.receive_command() == "yes buddy"
    assert link.receive_command() == ""
    client.close()


def test_close_releases_the_port():
    link = TelemetryLink(0, host="127.0.0.1", wait_for_client=False)
    port = link._server.getsockname()[1]
    link.close()
    # Binding again must succeed, i.e. the socket was really released.
    probe = TelemetryLink(port, host="127.0.0.1", wait_for_client=False)
    probe.close()
