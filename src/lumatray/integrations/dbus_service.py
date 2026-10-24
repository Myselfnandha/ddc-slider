"""
UNIX socket IPC service and D-Bus integration for single-instance control and external scripting.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
from typing import Any, Callable, Dict, Optional

from ..storage.migrations import LUMATRAY_CONFIG_DIR

logger = logging.getLogger(__name__)

IPC_SOCKET_PATH = os.path.join(LUMATRAY_CONFIG_DIR, "ipc.sock")


def send_ipc_command(command: Dict[str, Any], timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    """Send a command to a running LumaTray daemon via UNIX domain socket."""
    if not os.path.exists(IPC_SOCKET_PATH):
        return None

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect(IPC_SOCKET_PATH)
        data = json.dumps(command) + "\n"
        sock.sendall(data.encode("utf-8"))

        response_raw = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response_raw += chunk
            if b"\n" in response_raw:
                break

        if response_raw:
            return json.loads(response_raw.decode("utf-8").strip())
    except (socket.error, ConnectionRefusedError, json.JSONDecodeError) as e:
        logger.debug(f"IPC connection failed: {e}")
        # Clean up stale socket if connection refused
        if isinstance(e, ConnectionRefusedError) and os.path.exists(IPC_SOCKET_PATH):
            try:
                os.remove(IPC_SOCKET_PATH)
            except OSError:
                pass
    finally:
        sock.close()

    return None


class IPCServer:
    """Listens on a UNIX domain socket and dispatches commands to handler callbacks."""

    def __init__(self, request_handler: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self.request_handler = request_handler
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    def start(self) -> None:
        """Start the IPC server in a background thread."""
        os.makedirs(os.path.dirname(IPC_SOCKET_PATH), exist_ok=True)
        if os.path.exists(IPC_SOCKET_PATH):
            try:
                os.remove(IPC_SOCKET_PATH)
            except OSError:
                pass

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(IPC_SOCKET_PATH)
        self._sock.listen(5)
        self._running = True

        self._thread = threading.Thread(target=self._server_loop, name="LumaTrayIPCServer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the IPC server and remove socket."""
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        if os.path.exists(IPC_SOCKET_PATH):
            try:
                os.remove(IPC_SOCKET_PATH)
            except OSError:
                pass

    def _server_loop(self):
        while self._running:
            try:
                conn, _ = self._sock.accept()
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
            except Exception:
                if not self._running:
                    break

    def _handle_client(self, conn: socket.socket):
        with conn:
            try:
                conn.settimeout(3.0)
                buffer = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buffer += chunk
                    if b"\n" in buffer:
                        break

                if buffer:
                    req = json.loads(buffer.decode("utf-8").strip())
                    resp = self.request_handler(req)
                    resp_data = json.dumps(resp) + "\n"
                    conn.sendall(resp_data.encode("utf-8"))
            except Exception as e:
                logger.error(f"Error handling IPC client request: {e}")
