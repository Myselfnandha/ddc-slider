from lumatray.core.models import (
    CapabilityReport,
    DisplayIdentity,
    DisplayType,
    MonitorState,
    Profile,
    VCPFeature,
)


def test_display_identity_serialization():
    disp = DisplayIdentity(
        id="ddc_test123",
        name="Dell UltraSharp",
        display_type=DisplayType.EXTERNAL_DDC,
        bus=7,
        device_path="/dev/i2c-7",
        connector_name="DP-1",
        manufacturer="Dell",
        model="U2720Q",
        serial="SN12345",
        edid_hash="abc12345",
        is_internal=False,
    )
    d = disp.to_dict()
    assert d["id"] == "ddc_test123"
    assert d["display_type"] == "external_ddc"
    assert d["bus"] == 7

    restored = DisplayIdentity.from_dict(d)
    assert restored.id == disp.id
    assert restored.display_type == DisplayType.EXTERNAL_DDC
    assert restored.model == "U2720Q"


def test_capability_report():
    feat10 = VCPFeature(code=0x10, name="Brightness", is_continuous=True)
    feat14 = VCPFeature(code=0x14, name="Color Preset", is_continuous=False, supported_values={1: "sRGB", 5: "6500K"})
    report = CapabilityReport(
        display_id="ddc_test123",
        ddc_version="2.1",
        features={0x10: feat10, 0x14: feat14},
    )
    assert report.supports(0x10) is True
    assert report.supports(0x12) is False
    assert report.supports(0x14) is True
    assert report.get_feature(0x14).supported_values[5] == "6500K"


def test_profile_serialization():
    prof = Profile(
        id="test_movie",
        name="Movie Night",
        master_brightness=40,
        master_contrast=60,
        master_color_temp=3500,
        is_system=False,
    )
    data = prof.to_dict()
    assert data["id"] == "test_movie"
    assert data["master_brightness"] == 40

    loaded = Profile.from_dict(data)
    assert loaded.name == "Movie Night"
    assert loaded.master_color_temp == 3500
