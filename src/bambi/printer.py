"""Talk to the P1S over LAN mode (MQTT for status/commands, FTPS for uploads)."""

import time
from contextlib import contextmanager
from pathlib import Path

import bambulabs_api as bl

from bambi import ams
from bambi.config import get_settings


class PrinterConfigError(RuntimeError):
    pass


@contextmanager
def connect(timeout: float = 15.0):
    s = get_settings()
    if not (s.bambu_ip and s.bambu_access_code and s.bambu_serial):
        raise PrinterConfigError(
            "set BAMBU_IP, BAMBU_ACCESS_CODE and BAMBU_SERIAL in .env "
            "(printer screen: Settings > LAN Only / Network)"
        )
    printer = bl.Printer(s.bambu_ip, s.bambu_access_code, s.bambu_serial)
    printer.mqtt_start()
    try:
        deadline = time.monotonic() + timeout
        while not printer.mqtt_client_ready():
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"no MQTT response from {s.bambu_ip} after {timeout:.0f}s "
                    "(check BAMBU_SERIAL and BAMBU_ACCESS_CODE)"
                )
            time.sleep(0.25)
        # "ready" trips on the echo of our own request, and the printer ignores the
        # pushall sent during the handshake. Ask again and wait for a full report.
        printer.mqtt_client.pushall()
        while "gcode_state" not in printer.mqtt_client._data.get("print", {}):
            if time.monotonic() > deadline:
                raise TimeoutError(f"no full status from {s.bambu_ip}")
            time.sleep(0.25)
        yield printer
    finally:
        printer.mqtt_stop()


def trays(printer: bl.Printer) -> list[ams.Tray]:
    """Loaded AMS trays plus the external spool, as the printer reports them now."""
    try:
        hub = printer.ams_hub()
    except (AttributeError, KeyError, TypeError, ValueError):
        hub = bl.AMSHub()  # AMS absent or not reported yet
    try:
        external = printer.vt_tray()
    except (AttributeError, KeyError, TypeError, ValueError):
        external = None
    return ams.trays_from(hub, external)


def status(printer: bl.Printer) -> dict:
    return {
        "state": str(printer.get_state()),
        "stage": str(printer.get_current_state()),
        "file": printer.get_file_name() or printer.subtask_name(),
        "percent": printer.get_percentage(),
        "remaining_min": printer.get_time(),
        "layer": f"{printer.current_layer_num()}/{printer.total_layer_num()}",
        "nozzle_c": printer.get_nozzle_temperature(),
        "bed_c": printer.get_bed_temperature(),
        "ams": trays(printer),
    }


def send(
    printer: bl.Printer,
    file: Path,
    start: bool,
    ams_mapping: list[int] | None = None,
    plate: int = 1,
) -> str:
    """Upload, optionally start. ams_mapping[i] = AMS tray for filament i+1 (-1 = external)."""
    mapping = ams_mapping or [0]
    with file.open("rb") as fh:
        result = printer.upload_file(fh, file.name)
    if "226" not in str(result):  # FTP "transfer complete"
        raise RuntimeError(f"upload failed: {result}")
    if start:
        use_ams = all(slot >= 0 for slot in mapping)
        ok = printer.start_print(
            file.name, plate, use_ams=use_ams, ams_mapping=mapping if use_ams else [0]
        )
        if not ok:
            raise RuntimeError("printer rejected start command")
    return file.name
