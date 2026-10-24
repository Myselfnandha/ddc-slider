from lumatray.backends.color_x11 import kelvin_to_rgb


def test_kelvin_to_rgb_mapping():
    # 6500K is neutral daylight -> (1.0, 1.0, 1.0)
    r_6500, g_6500, b_6500 = kelvin_to_rgb(6500)
    assert r_6500 == 1.0
    assert g_6500 == 1.0
    assert b_6500 == 1.0

    # Warm night (2700K) -> high red, reduced green, strongly attenuated blue
    r_warm, g_warm, b_warm = kelvin_to_rgb(2700)
    assert r_warm == 1.0
    assert g_warm < 0.85
    assert b_warm < 0.45

    # Candlelight (2200K) -> blue very low
    r_candle, g_candle, b_candle = kelvin_to_rgb(2200)
    assert r_candle == 1.0
    assert b_candle < 0.3

    # High Kelvin (10000K) -> blue is maximum
    r_cool, g_cool, b_cool = kelvin_to_rgb(10000)
    assert b_cool == 1.0
    assert r_cool < 1.0
