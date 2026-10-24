from lumatray.core.errors import ValidationError
from lumatray.core.validation import (
    DESTRUCTIVE_VCP_CODES,
    SAFE_VCP_ALLOWLIST,
    clamp_brightness,
    clamp_contrast,
    clamp_kelvin,
    clamp_rgb_gain,
    is_destructive_vcp,
    validate_vcp_request,
)


def test_clamping():
    assert clamp_brightness(-10) == 0
    assert clamp_brightness(150) == 100
    assert clamp_brightness(75) == 75

    assert clamp_contrast(-5) == 0
    assert clamp_contrast(110) == 100
    assert clamp_contrast(50) == 50

    assert clamp_kelvin(500) == 1000
    assert clamp_kelvin(12000) == 10000
    assert clamp_kelvin(4200) == 4200

    assert clamp_rgb_gain(-1) == 0
    assert clamp_rgb_gain(105) == 100
    assert clamp_rgb_gain(90) == 90


def test_destructive_vcp_codes_blocked():
    for code in DESTRUCTIVE_VCP_CODES:
        assert is_destructive_vcp(code) is True
        raised = False
        try:
            validate_vcp_request(code, 1)
        except ValidationError:
            raised = True
        assert raised is True



def test_safe_vcp_codes_allowed():
    for code in (0x10, 0x12, 0x0C, 0x14, 0x16, 0x18, 0x1A, 0x60):
        assert code in SAFE_VCP_ALLOWLIST
        assert is_destructive_vcp(code) is False
        validate_vcp_request(code, 50)
