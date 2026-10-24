"""
Custom exception hierarchy for LumaTray.
"""

class LumaTrayError(Exception):
    """Base exception for all LumaTray errors."""
    pass


class DDCError(LumaTrayError):
    """Raised when a DDC/CI communication error occurs."""
    def __init__(self, message: str, bus: int | None = None, feature: int | None = None):
        super().__init__(message)
        self.bus = bus
        self.feature = feature


class PermissionError(LumaTrayError):
    """Raised when user lacks permissions for /dev/i2c-* or backlight."""
    def __init__(self, message: str, device: str | None = None):
        super().__init__(message)
        self.device = device


class UnsupportedFeatureError(LumaTrayError):
    """Raised when a VCP or hardware feature is not supported by the monitor."""
    def __init__(self, message: str, feature_code: int | None = None, display_id: str | None = None):
        super().__init__(message)
        self.feature_code = feature_code
        self.display_id = display_id


class BackendUnavailableError(LumaTrayError):
    """Raised when a required backend tool (e.g. ddcutil, brightnessctl, xrandr) is missing."""
    def __init__(self, backend_name: str, reason: str = ""):
        super().__init__(f"Backend '{backend_name}' is unavailable: {reason}")
        self.backend_name = backend_name


class HardwareTimeoutError(DDCError):
    """Raised when a hardware operation times out."""
    pass


class ValidationError(LumaTrayError):
    """Raised when an operation request fails safety or range validation."""
    pass


class ProfileError(LumaTrayError):
    """Raised when a profile cannot be loaded, saved, or applied."""
    pass


class IPCError(LumaTrayError):
    """Raised during IPC communication with running instance."""
    pass
