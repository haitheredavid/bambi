import zipfile
from types import SimpleNamespace

import pytest

from bambi import printer


def make_3mf(path, plates):
    with zipfile.ZipFile(path, "w") as z:
        for n in plates:
            z.writestr(f"Metadata/plate_{n}.gcode", "G28")
            z.writestr(f"Metadata/plate_{n}.gcode.md5", "x")
            z.writestr(f"Metadata/plate_{n}.png", "x")
    return path


def test_plates_lists_sliced_gcode(tmp_path):
    assert printer.plates(make_3mf(tmp_path / "a.gcode.3mf", [2, 1])) == [1, 2]


class FakePrinter:
    def __init__(self, states, subtask="other.gcode.3mf", error=0, hms=()):
        self.states = iter(states)
        self.state = "FINISH"
        self.subtask = subtask
        self.error = error
        self.mqtt_client = SimpleNamespace(_data={"print": {"hms": list(hms)}})

    def get_state(self):
        self.state = next(self.states, self.state)
        return self.state

    def subtask_name(self):
        return self.subtask

    def print_error_code(self):
        return self.error


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(printer.time, "sleep", lambda s: None)


def test_wait_started_returns_once_running():
    p = FakePrinter(["FINISH", "PREPARE"], subtask="job.gcode.3mf")
    printer.wait_started(p, "job.gcode.3mf", since=0)


def test_wait_started_reports_ignored_start_with_new_hms():
    hms = [
        {"attr": 0x05000500, "code": 0x00010007, "timestamp": 200},
        {"attr": 0x03000100, "code": 0x00020001, "timestamp": 50},  # older alert
    ]
    p = FakePrinter([], error=0x05004001, hms=hms)
    with pytest.raises(RuntimeError, match="HMS_0500_0500_0001_0007\\)") as e:
        printer.wait_started(p, "job.gcode.3mf", since=100)
    assert "0300" not in str(e.value)


def test_wait_started_times_out_when_printer_ignores_command(monkeypatch):
    clock = iter(range(0, 1000, 10))
    monkeypatch.setattr(printer.time, "monotonic", lambda: next(clock))
    with pytest.raises(RuntimeError, match="did not start job.gcode.3mf"):
        printer.wait_started(FakePrinter([]), "job.gcode.3mf", since=0, timeout=30)
