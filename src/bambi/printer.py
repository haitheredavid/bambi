"""Talk to the P1S over LAN mode (MQTT for status/commands, FTPS for uploads)."""

import time
from contextlib import contextmanager
from pathlib import Path

import bambulabs_api as bl

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
                    f"no MQTT response from {s.bambu_ip} after {timeout:.0f}s"
                )
            time.sleep(0.25)
        # First full status push can lag the connection slightly.
        time.sleep(1.0)
        yield printer
    finally:
        printer.mqtt_stop()


def status(printer: bl.Printer) -> dict:
    trays = []
    try:
        for ams_id, ams in printer.ams_hub().ams_hub.items():
            for tray_id, tray in ams.filament_trays.items():
                trays.append(
                    {
                        "slot": int(ams_id) * 4 + int(tray_id),
                        "type": tray.tray_type,
                        "color": tray.tray_color,
                    }
                )
    except (AttributeError, KeyError, TypeError, ValueError):
        trays = []  # AMS absent or not reported yet
    return {
        "state": str(printer.get_state()),
        "stage": str(printer.get_current_state()),
        "file": printer.get_file_name() or printer.subtask_name(),
        "percent": printer.get_percentage(),
        "remaining_min": printer.get_time(),
        "layer": f"{printer.current_layer_num()}/{printer.total_layer_num()}",
        "nozzle_c": printer.get_nozzle_temperature(),
        "bed_c": printer.get_bed_temperature(),
        "ams": trays,
    }


def send(
    printer: bl.Printer, file: Path, start: bool, ams_slot: int = 0, plate: int = 1
) -> str:
    with file.open("rb") as fh:
        result = printer.upload_file(fh, file.name)
    if "226" not in str(result):  # FTP "transfer complete"
        raise RuntimeError(f"upload failed: {result}")
    if start:
        use_ams = ams_slot >= 0
        ok = printer.start_print(
            file.name, plate, use_ams=use_ams, ams_mapping=[ams_slot if use_ams else 0]
        )
        if not ok:
            raise RuntimeError("printer rejected start command")
    return file.name
