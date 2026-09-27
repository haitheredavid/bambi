"""Talk to the P1S over LAN mode (MQTT for status/commands, FTPS for uploads)."""

import re
import time
import zipfile
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


def plates(file: Path) -> list[int]:
    """Plate numbers sliced into a .gcode.3mf (Metadata/plate_<n>.gcode)."""
    with zipfile.ZipFile(file) as z:
        names = z.namelist()
    found = (re.fullmatch(r"Metadata/plate_(\d+)\.gcode", n) for n in names)
    return sorted(int(m.group(1)) for m in found if m)


def hms_codes(printer: bl.Printer, since: float = 0) -> list[str]:
    """HMS alerts newer than `since` (unix time), as HMS_XXXX_XXXX_XXXX_XXXX."""
    out = []
    for h in printer.mqtt_client._data.get("print", {}).get("hms", []):
        if h.get("timestamp", 0) < since:
            continue
        a, c = f"{h['attr']:08X}", f"{h['code']:08X}"
        out.append(f"HMS_{a[:4]}_{a[4:]}_{c[:4]}_{c[4:]}")
    return out


def wait_started(printer: bl.Printer, name: str, since: float, timeout: float = 45.0):
    """Wait until the printer is preparing/running `name`; raise if it never does.

    start_print only publishes the MQTT command, so a printer that ignores it
    (LAN mode without Developer Mode) otherwise looks like a successful start.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if printer.subtask_name() == name and str(printer.get_state()) in (
            "PREPARE",
            "RUNNING",
        ):
            return
        if printer.print_error_code():
            break
        time.sleep(1)
    hms = hms_codes(printer, since)
    raise RuntimeError(
        f"printer did not start {name} (state {printer.get_state()}"
        + (f", {', '.join(hms)}" if hms else "")
        + "); LAN start needs Developer Mode. The file is uploaded: "
        "start it from the printer screen"
    )


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
        sent_at = time.time() - 5  # printer clock skew
        ok = printer.start_print(
            file.name, plate, use_ams=use_ams, ams_mapping=mapping if use_ams else [0]
        )
        if not ok:
            raise RuntimeError("printer rejected start command")
        wait_started(printer, file.name, sent_at)
    return file.name
