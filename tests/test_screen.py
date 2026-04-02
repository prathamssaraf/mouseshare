"""Tests for screen geometry helpers."""

import pytest
from unittest.mock import patch

from mouseshare.input.screen import normalise, denormalise, detect_edge
from mouseshare.constants import DIR_LEFT, DIR_RIGHT, DIR_TOP, DIR_BOTTOM, EDGE_THRESHOLD


FAKE_W, FAKE_H = 1920, 1080


@pytest.fixture(autouse=True)
def mock_screen(monkeypatch):
    monkeypatch.setattr("mouseshare.input.screen.get_screen_size", lambda: (FAKE_W, FAKE_H))


def test_normalise_corners():
    assert normalise(0, 0)           == (0.0, 0.0)
    assert normalise(FAKE_W, FAKE_H) == (1.0, 1.0)


def test_normalise_centre():
    nx, ny = normalise(FAKE_W // 2, FAKE_H // 2)
    assert abs(nx - 0.5) < 0.001
    assert abs(ny - 0.5) < 0.001


def test_round_trip():
    for x, y in [(0, 0), (100, 200), (1919, 1079), (960, 540)]:
        nx, ny = normalise(x, y)
        rx, ry = denormalise(nx, ny)
        assert abs(rx - x) <= 1
        assert abs(ry - y) <= 1


def test_detect_edge_left():
    assert detect_edge(0, 500)            == DIR_LEFT
    assert detect_edge(EDGE_THRESHOLD, 500) == DIR_LEFT


def test_detect_edge_right():
    assert detect_edge(FAKE_W - 1, 500)                     == DIR_RIGHT
    assert detect_edge(FAKE_W - 1 - EDGE_THRESHOLD, 500)    == DIR_RIGHT


def test_detect_edge_top():
    assert detect_edge(500, 0)            == DIR_TOP
    assert detect_edge(500, EDGE_THRESHOLD) == DIR_TOP


def test_detect_edge_bottom():
    assert detect_edge(500, FAKE_H - 1)                     == DIR_BOTTOM
    assert detect_edge(500, FAKE_H - 1 - EDGE_THRESHOLD)    == DIR_BOTTOM


def test_no_edge_middle():
    assert detect_edge(FAKE_W // 2, FAKE_H // 2) is None


def test_no_edge_just_inside():
    assert detect_edge(EDGE_THRESHOLD + 1, EDGE_THRESHOLD + 1) is None
