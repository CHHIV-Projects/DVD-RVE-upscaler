from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

NVIDIA_QUERY = [
    "nvidia-smi",
    "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw,power.limit,fan.speed",
    "--format=csv,noheader,nounits",
]

# Query the known AMD CPU sensor chip directly rather than enumerating all
# sensors. Unrestricted `sensors -j` also probes unrelated hardware sensors
# (e.g. the MT7921 Wi-Fi thermal sensor), which can hang indefinitely in the
# kernel on affected systems.
CPU_SENSOR_CHIP = "k10temp-pci-00c3"
SENSORS_QUERY = ["sensors", "-j", CPU_SENSOR_CHIP]


def _number(value: str) -> float | None:
    normalized = value.strip()
    if not normalized or normalized.lower() in {"n/a", "[n/a]", "not supported"}:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def parse_nvidia_smi_csv(output: str) -> dict[str, float | None]:
    line = next((line.strip() for line in output.splitlines() if line.strip()), "")
    fields = [field.strip() for field in line.split(",")]
    if len(fields) != 7:
        raise ValueError("NVIDIA telemetry output did not contain the expected fields.")
    values = [_number(field) for field in fields]
    return {
        "temperature_c": values[0],
        "utilization_percent": values[1],
        "memory_used_mib": values[2],
        "memory_total_mib": values[3],
        "power_draw_w": values[4],
        "power_limit_w": values[5],
        "fan_percent": values[6],
    }


def parse_cpu_stat(text: str) -> tuple[int, int]:
    line = next((line for line in text.splitlines() if line.startswith("cpu ")), "")
    fields = line.split()
    if len(fields) < 5:
        raise ValueError("/proc/stat did not contain aggregate CPU counters.")
    counters = [int(value) for value in fields[1:]]
    idle = counters[3] + (counters[4] if len(counters) > 4 else 0)
    return sum(counters), idle


def calculate_cpu_utilization(
    previous: tuple[int, int],
    current: tuple[int, int],
) -> float | None:
    total_delta = current[0] - previous[0]
    idle_delta = current[1] - previous[1]
    if total_delta <= 0 or idle_delta < 0:
        return None
    return round(max(0.0, min(100.0, (total_delta - idle_delta) * 100.0 / total_delta)), 1)


def parse_sensors_temperature(output: str) -> float | None:
    payload = json.loads(output)
    if not isinstance(payload, dict):
        return None
    for chip_name, chip in payload.items():
        if not str(chip_name).lower().startswith("k10temp-") or not isinstance(chip, dict):
            continue
        tctl = chip.get("Tctl")
        if not isinstance(tctl, dict):
            continue
        for key, value in tctl.items():
            if str(key).endswith("_input") and isinstance(value, (int, float)):
                return float(value)
    return None


class TelemetryService:
    def __init__(
        self,
        *,
        runner: Callable[..., Any] = subprocess.run,
        proc_stat_reader: Callable[[], str] | None = None,
    ):
        self.runner = runner
        self.proc_stat_reader = proc_stat_reader or (
            lambda: Path("/proc/stat").read_text(encoding="utf-8")
        )
        self._lock = threading.Lock()
        self._previous_cpu = self._read_cpu_counters()

    def _read_cpu_counters(self) -> tuple[int, int] | None:
        try:
            return parse_cpu_stat(self.proc_stat_reader())
        except (OSError, TypeError, ValueError):
            return None

    def _cpu_utilization(self) -> float | None:
        with self._lock:
            current = self._read_cpu_counters()
            previous = self._previous_cpu
            self._previous_cpu = current
        if previous is None or current is None:
            return None
        return calculate_cpu_utilization(previous, current)

    def _gpu(self) -> tuple[dict[str, float | None], str | None]:
        unavailable = {
            "temperature_c": None,
            "utilization_percent": None,
            "memory_used_mib": None,
            "memory_total_mib": None,
            "power_draw_w": None,
            "power_limit_w": None,
            "fan_percent": None,
        }
        try:
            result = self.runner(
                NVIDIA_QUERY,
                capture_output=True,
                text=True,
                check=False,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return unavailable, f"NVIDIA telemetry unavailable: {exc}"
        if result.returncode != 0:
            return unavailable, "NVIDIA telemetry command failed."
        try:
            return parse_nvidia_smi_csv(result.stdout or ""), None
        except ValueError as exc:
            return unavailable, str(exc)

    def _cpu_temperature(self) -> tuple[float | None, str | None]:
        try:
            result = self.runner(
                SENSORS_QUERY,
                capture_output=True,
                text=True,
                check=False,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, f"CPU temperature unavailable: {exc}"
        if result.returncode != 0:
            return None, "CPU temperature command failed."
        try:
            temperature = parse_sensors_temperature(result.stdout or "")
        except (json.JSONDecodeError, TypeError):
            return None, "CPU temperature output was not valid sensors JSON."
        if temperature is None:
            return None, "AMD k10temp Tctl was unavailable."
        return temperature, None

    def snapshot(self) -> dict[str, Any]:
        gpu, gpu_reason = self._gpu()
        cpu_temperature, cpu_temperature_reason = self._cpu_temperature()
        cpu_utilization = self._cpu_utilization()
        reasons = [
            reason
            for reason in (
                gpu_reason,
                cpu_temperature_reason,
                "CPU utilization is awaiting a second sample."
                if cpu_utilization is None
                else None,
            )
            if reason
        ]
        return {
            "status": "partial" if reasons else "ok",
            "cpu": {
                "utilization_percent": cpu_utilization,
                "temperature_c": cpu_temperature,
            },
            "gpu": gpu,
            "unavailable_reasons": reasons,
            "polling_guidance_seconds": 3,
        }
