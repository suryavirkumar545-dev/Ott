from app.utils.formatters import (format_duration, format_eta, format_percentage,
                                  format_size, format_speed, pretty_name, progress_bar)


def test_size():
    assert format_size(512 * 1024) == "512 KB"
    assert format_size(12.4 * 1024 * 1024) == "12.4 MB"
    assert format_size(1.42 * 1024**3) == "1.42 GB"


def test_speed_duration_eta():
    assert format_speed(23.4 * 1024 * 1024) == "23.4 MB/s"
    assert format_duration(13) == "00:13"
    assert format_duration(3725) == "01:02:05"
    assert format_eta(None) == "--:--"
    assert format_percentage(1, 4) == "25%"


def test_bar_fixed_width():
    widths = {len(progress_bar(i, 100).split()[0]) for i in range(0, 101, 7)}
    assert widths == {16}


def test_pretty_name():
    n = pretty_name("Toonworld4all_Spy_x_Family_S01E24_720p_x264_BDRip_Multi_Audio_ESub.mkv")
    assert n.endswith(".mkv") and len(n) <= 48 and "_" not in n
