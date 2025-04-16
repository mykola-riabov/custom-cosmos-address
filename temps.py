#!/usr/bin/python3
import psutil
import GPUtil

def get_temps():
    cpu_temp = "-"
    gpu_temp = "-"
    try:
        temps = psutil.sensors_temperatures()
        for name in ["k10temp", "coretemp", "acpitz", "cpu_thermal"]:
            entries = temps.get(name)
            if entries:
                cpu_temp = f"{entries[0].current:.1f}°C"
                break
    except Exception:
        pass
    try:
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu_temp = f"{gpus[0].temperature}°C"
    except Exception:
        pass
    return cpu_temp, gpu_temp

