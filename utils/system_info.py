"""
utils/system_info.py
--------------------
Dynamic, cross-platform hardware and operating system detection.
Works natively on macOS, Windows 10/11, and Linux.

Uses Python standard libraries (platform, sys, os, ctypes) with graceful
fallbacks. Never hardcodes machine specifications.
"""

import os
import platform
import sys
from typing import Dict, Any


def get_os_info() -> Dict[str, str]:
    """
    Detects the host operating system and version.

    Returns:
        dict: Containing 'name', 'version', and 'family'.
    """
    system_name = platform.system()
    version_str = ""

    if system_name == "Darwin":
        display_name = "macOS"
        mac_ver = platform.mac_ver()[0]
        version_str = f"macOS {mac_ver}" if mac_ver else "macOS"
    elif system_name == "Windows":
        display_name = "Windows"
        win_ver = platform.win32_ver()[0]
        version_str = f"Windows {win_ver}" if win_ver else "Windows"
    elif system_name == "Linux":
        display_name = "Linux"
        # Attempt to read Linux distribution from /etc/os-release if available
        distro = "Linux"
        try:
            if os.path.exists("/etc/os-release"):
                with open("/etc/os-release", "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            distro = line.strip().split("=")[1].replace('"', '')
                            break
        except Exception:
            distro = f"Linux {platform.release()}"
        version_str = distro
    else:
        display_name = system_name or "Unknown OS"
        version_str = platform.release() or display_name

    return {
        "name": display_name,
        "version": version_str,
        "raw_system": system_name,
    }


def get_cpu_info() -> Dict[str, str]:
    """
    Detects processor architecture and model.

    Returns:
        dict: Containing 'arch' (e.g. ARM64, x86_64) and 'processor'.
    """
    machine = platform.machine()
    processor = platform.processor()

    # Standardize architecture labeling
    arch_display = machine
    if machine.lower() in ["arm64", "aarch64"]:
        arch_display = "ARM64"
    elif machine.lower() in ["x86_64", "amd64"]:
        arch_display = "x86_64 (64-bit)"
    elif machine.lower() in ["x86", "i386", "i686"]:
        arch_display = "x86 (32-bit)"

    return {
        "arch": arch_display,
        "processor": processor if processor else arch_display,
    }


def get_ram_info() -> str:
    """
    Detects total installed physical RAM using standard libraries
    with psutil and platform fallbacks.

    Returns:
        str: Formatted RAM string (e.g. "8.0 GB", "16.0 GB") or "Unavailable".
    """
    # 1. Try psutil if installed in the environment
    try:
        import psutil
        total_bytes = psutil.virtual_memory().total
        if total_bytes > 0:
            return f"{round(total_bytes / (1024 ** 3), 1)} GB"
    except Exception:
        pass

    # 2. Try POSIX sysconf (macOS, Linux, BSD)
    try:
        if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names and "SC_PHYS_PAGES" in os.sysconf_names:
            page_size = os.sysconf("SC_PAGE_SIZE")
            phys_pages = os.sysconf("SC_PHYS_PAGES")
            total_bytes = page_size * phys_pages
            if total_bytes > 0:
                return f"{round(total_bytes / (1024 ** 3), 1)} GB"
    except Exception:
        pass

    # 3. Try Windows ctypes GlobalMemoryStatusEx
    if platform.system() == "Windows":
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return f"{round(stat.ullTotalPhys / (1024 ** 3), 1)} GB"
        except Exception:
            pass

    return "Unavailable"


def get_system_summary() -> Dict[str, Any]:
    """
    Generates a consolidated summary of system details for UI display.
    """
    os_info = get_os_info()
    cpu_info = get_cpu_info()
    ram_str = get_ram_info()

    return {
        "os_name": os_info["name"],
        "os_version": os_info["version"],
        "arch": cpu_info["arch"],
        "processor": cpu_info["processor"],
        "ram": ram_str,
        "python_version": sys.version.split()[0],
    }
