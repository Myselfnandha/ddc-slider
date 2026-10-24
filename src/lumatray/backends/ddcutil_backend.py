"""
DDC/CI hardware backend via ddcutil with serialized per-bus queues and coalesced writes.
"""

from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
from typing import Dict, Optional, Tuple

from ..core.errors import DDCError, HardwareTimeoutError, ValidationError
from ..core.models import OperationResult
from ..core.validation import is_destructive_vcp, validate_vcp_request

logger = logging.getLogger(__name__)


class DDCBusWorker:
    """Manages serialized operations for a single physical I2C bus."""

    def __init__(self, bus: int):
        self.bus = bus
        self.lock = threading.Lock()
        self._target_values: Dict[int, int] = {}
        self._target_lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None
        self._last_written: Dict[int, int] = {}

    def get_last_written(self, feature: int) -> Optional[int]:
        with self._target_lock:
            return self._last_written.get(feature)

    def queue_set(self, feature: int, value: int, on_complete: Optional[callable] = None) -> None:
        """Queue a write request. If a write is currently in progress, replaces pending target with newest."""
        with self._target_lock:
            if self._last_written.get(feature) == value and feature not in self._target_values:
                # Value is already confirmed on hardware, no-op
                if on_complete:
                    on_complete(OperationResult(success=True, verified=True, feature_code=feature, actual_value=value))
                return

            self._target_values[feature] = value
            if self._worker_thread is None or not self._worker_thread.is_alive():
                self._worker_thread = threading.Thread(
                    target=self._worker_loop, name=f"DDCWorker-bus{self.bus}", daemon=True
                )
                self._worker_thread.start()

    def _worker_loop(self):
        while True:
            with self._target_lock:
                if not self._target_values:
                    self._worker_thread = None
                    break
                # Pop next feature to write
                feat, val = next(iter(self._target_values.items()))
                del self._target_values[feat]

            # Skip write if already identical to hardware
            if self._last_written.get(feat) == val:
                continue

            # Perform serialized hardware write
            t0 = time.time()
            feat_hex = f"0x{feat:02x}"
            success = False
            with self.lock:
                try:
                    cmd = ["ddcutil", "setvcp", feat_hex, str(val), "--bus", str(self.bus)]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
                    success = (res.returncode == 0)
                    if success:
                        with self._target_lock:
                            self._last_written[feat] = val
                    else:
                        logger.warning(f"DDC setvcp error on bus {self.bus} feature {feat_hex}: {res.stderr.strip()}")
                except Exception as e:
                    logger.error(f"DDC write exception on bus {self.bus}: {e}")

            latency = (time.time() - t0) * 1000.0
            logger.debug(f"DDC bus {self.bus} write {feat_hex}={val} took {latency:.1f}ms (success={success})")


class DDCUtilBackend:
    """Central DDC/CI interface managing all physical I2C buses."""

    def __init__(self):
        self._bus_workers: Dict[int, DDCBusWorker] = {}
        self._lock = threading.Lock()

    def _get_worker(self, bus: int) -> DDCBusWorker:
        with self._lock:
            if bus not in self._bus_workers:
                self._bus_workers[bus] = DDCBusWorker(bus)
            return self._bus_workers[bus]

    def get_vcp(self, bus: int, feature: int) -> Optional[int]:
        """Synchronously query a VCP feature from the monitor."""
        if is_destructive_vcp(feature):
            raise ValidationError(f"Cannot read destructive VCP code 0x{feature:02x}")

        worker = self._get_worker(bus)
        feat_hex = f"0x{feature:02x}"
        with worker.lock:
            try:
                cmd = ["ddcutil", "getvcp", feat_hex, "--bus", str(bus), "--terse"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
                if res.returncode != 0:
                    return None

                # Formats: "VCP 10 C 60 100" or "current value = 60"
                m = re.search(r'VCP\s+[0-9a-fA-F]+\s+\w+\s+(\d+)\s+(\d+)', res.stdout)
                if m:
                    val = int(m.group(1))
                    with worker._target_lock:
                        worker._last_written[feature] = val
                    return val

                m = re.search(r'current value\s*=\s*(\d+)', res.stdout)
                if m:
                    val = int(m.group(1))
                    with worker._target_lock:
                        worker._last_written[feature] = val
                    return val
                return None
            except subprocess.TimeoutExpired:
                raise HardwareTimeoutError(f"Timeout querying VCP {feat_hex} on bus {bus}", bus=bus, feature=feature)
            except Exception as e:
                logger.error(f"Error querying VCP {feat_hex} on bus {bus}: {e}")
                return None

    def set_vcp(self, bus: int, feature: int, value: int, async_write: bool = True) -> OperationResult:
        """Set a VCP feature value."""
        validate_vcp_request(feature, value, allow_extended=True)
        worker = self._get_worker(bus)

        if async_write:
            worker.queue_set(feature, value)
            return OperationResult(
                success=True,
                verified=False,
                feature_code=feature,
                requested_value=value,
                actual_value=value,
            )

        # Synchronous write
        t0 = time.time()
        feat_hex = f"0x{feature:02x}"
        with worker.lock:
            try:
                cmd = ["ddcutil", "setvcp", feat_hex, str(value), "--bus", str(bus)]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=7)
                success = (res.returncode == 0)
                latency = (time.time() - t0) * 1000.0
                if success:
                    with worker._target_lock:
                        worker._last_written[feature] = value
                    return OperationResult(
                        success=True,
                        verified=True,
                        feature_code=feature,
                        requested_value=value,
                        actual_value=value,
                        latency_ms=latency,
                    )
                else:
                    return OperationResult(
                        success=False,
                        verified=False,
                        feature_code=feature,
                        requested_value=value,
                        error_message=res.stderr.strip() or "setvcp failed",
                        latency_ms=latency,
                    )
            except subprocess.TimeoutExpired:
                return OperationResult(
                    success=False,
                    verified=False,
                    feature_code=feature,
                    requested_value=value,
                    error_message=f"Timeout setting VCP {feat_hex} on bus {bus}",
                )
            except Exception as e:
                return OperationResult(
                    success=False,
                    verified=False,
                    feature_code=feature,
                    requested_value=value,
                    error_message=str(e),
                )


# Global singleton instance
ddc_backend = DDCUtilBackend()
