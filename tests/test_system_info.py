"""
tests/test_system_info.py
-------------------------
Unit tests verifying dynamic cross-platform system detection.
Validates:
1. get_os_info returns valid, non-empty OS details.
2. get_cpu_info returns valid architecture.
3. get_ram_info returns either a valid 'X.X GB' string or 'Unavailable' gracefully.
4. get_system_summary consolidates all values without crashing.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.system_info import get_os_info, get_cpu_info, get_ram_info, get_system_summary


def test_system_info_detection():
    print("Running Test: Validating dynamic system information detection...")

    os_info = get_os_info()
    assert os_info["name"] in ["macOS", "Windows", "Linux", "Darwin"], f"Unexpected OS name: {os_info['name']}"
    assert len(os_info["version"]) > 0, "OS version is empty"
    print(f"  ✅ OS Detected: {os_info['name']} ({os_info['version']})")

    cpu_info = get_cpu_info()
    assert len(cpu_info["arch"]) > 0, "CPU architecture is empty"
    print(f"  ✅ Architecture: {cpu_info['arch']}")

    ram = get_ram_info()
    assert ram == "Unavailable" or "GB" in ram, f"Unexpected RAM format: {ram}"
    print(f"  ✅ RAM Detected: {ram}")

    summary = get_system_summary()
    assert summary["os_name"] == os_info["name"], "Summary OS mismatch"
    assert summary["arch"] == cpu_info["arch"], "Summary arch mismatch"
    assert "python_version" in summary, "Summary missing python version"
    print("  ✅ System Summary validated successfully.")


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("🧪 SYSTEM INFO UNIT TEST")
    print("=" * 50 + "\n")
    test_system_info_detection()
    print("\n" + "=" * 50)
    print("🎉 ALL SYSTEM INFO TESTS PASSED!")
    print("=" * 50 + "\n")
