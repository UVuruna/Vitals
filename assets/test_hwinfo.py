"""Test script to read HWiNFO shared memory sensors."""

import ctypes
from ctypes import wintypes

kernel32 = ctypes.windll.kernel32

OpenFileMapping = kernel32.OpenFileMappingW
OpenFileMapping.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
OpenFileMapping.restype = wintypes.HANDLE

MapViewOfFile = kernel32.MapViewOfFile
MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
MapViewOfFile.restype = ctypes.c_void_p

UnmapViewOfFile = kernel32.UnmapViewOfFile
UnmapViewOfFile.argtypes = [ctypes.c_void_p]
UnmapViewOfFile.restype = wintypes.BOOL

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL

FILE_MAP_READ = 0x0004
HWINFO_SENSORS_SM = "Global\\HWiNFO_SENS_SM2"


# Define exact structures based on HWiNFO SDK
class HWiNFOHeader(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("dwSignature", ctypes.c_uint32),
        ("dwVersion", ctypes.c_uint32),
        ("dwRevision", ctypes.c_uint32),
        ("pollTime", ctypes.c_int64),
        ("dwOffsetOfSensorSection", ctypes.c_uint32),
        ("dwSizeOfSensorElement", ctypes.c_uint32),
        ("dwNumSensorElements", ctypes.c_uint32),
        ("dwOffsetOfReadingSection", ctypes.c_uint32),
        ("dwSizeOfReadingElement", ctypes.c_uint32),
        ("dwNumReadingElements", ctypes.c_uint32),
    ]


# Reading structure with 128-byte labels (SDK default)
class HWiNFOReading(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("dwSensorIndex", ctypes.c_uint32),
        ("dwReadingID", ctypes.c_uint32),
        ("dwReadingType", ctypes.c_uint32),
        ("szLabelOrig", ctypes.c_char * 128),
        ("szLabelUser", ctypes.c_char * 128),
        ("szUnit", ctypes.c_char * 16),
        ("Value", ctypes.c_double),
        ("ValueMin", ctypes.c_double),
        ("ValueMax", ctypes.c_double),
        ("ValueAvg", ctypes.c_double),
    ]


def test_hwinfo():
    print("=" * 60)
    print("HWiNFO Shared Memory Test")
    print("=" * 60)

    handle = OpenFileMapping(FILE_MAP_READ, False, HWINFO_SENSORS_SM)
    if not handle:
        print("[ERROR] Cannot open shared memory")
        print("Make sure HWiNFO is running with Shared Memory Support enabled")
        return

    base = MapViewOfFile(handle, FILE_MAP_READ, 0, 0, 0)
    if not base:
        print("[ERROR] Cannot map view")
        CloseHandle(handle)
        return

    print("[OK] Memory mapped!")

    # Read header
    header = HWiNFOHeader.from_address(base)

    print(f"\nVersion: {header.dwVersion}.{header.dwRevision}")
    print(f"Sensors: {header.dwNumSensorElements}")
    print(f"Readings: {header.dwNumReadingElements}")
    print(f"Reading size: {header.dwSizeOfReadingElement} (struct size: {ctypes.sizeof(HWiNFOReading)})")

    reading_offset = header.dwOffsetOfReadingSection
    reading_size = header.dwSizeOfReadingElement
    reading_count = header.dwNumReadingElements

    # Targets we're looking for
    targets = {
        "cpu (tctl/tdie)": "cpu_tctl",
        "cpu ccd1 (tdie)": "cpu_ccd1",
        "ambient": "ambient",
        "motherboard": "ambient",
        "dram read bandwidth": "dram_read",
        "dram write bandwidth": "dram_write",
    }

    print("\n" + "=" * 60)
    print("SEARCHING FOR TARGET SENSORS:")
    print("=" * 60)

    found = {}

    for i in range(reading_count):
        # Use actual reading_size for iteration, but read using SDK structure
        addr = base + reading_offset + i * reading_size
        reading = HWiNFOReading.from_address(addr)

        label = reading.szLabelOrig.decode('utf-8', errors='ignore').rstrip('\x00')
        unit = reading.szUnit.decode('utf-8', errors='ignore').rstrip('\x00')
        value = reading.Value

        # Check if this matches any target
        label_lower = label.lower()
        for target_key, target_name in targets.items():
            if target_key in label_lower:
                found[target_name] = {
                    "label": label,
                    "unit": unit,
                    "value": value,
                    "min": reading.ValueMin,
                    "max": reading.ValueMax,
                    "avg": reading.ValueAvg,
                }
                print(f"\n[{i}] {label}")
                print(f"    Value: {value:.2f} {unit}")
                print(f"    Min: {reading.ValueMin:.2f}, Max: {reading.ValueMax:.2f}, Avg: {reading.ValueAvg:.2f}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY:")
    print("=" * 60)

    for name, data in found.items():
        print(f"  {name}: {data['value']:.2f} {data['unit']}")

    # Also list first 15 readings to see what's available
    print("\n" + "=" * 60)
    print("FIRST 15 READINGS:")
    print("=" * 60)

    for i in range(min(15, reading_count)):
        addr = base + reading_offset + i * reading_size
        reading = HWiNFOReading.from_address(addr)
        label = reading.szLabelOrig.decode('utf-8', errors='ignore').rstrip('\x00')
        unit = reading.szUnit.decode('utf-8', errors='ignore').rstrip('\x00')
        value = reading.Value
        print(f"[{i:3d}] {label[:40]:40s} = {value:10.2f} {unit}")

    UnmapViewOfFile(base)
    CloseHandle(handle)


if __name__ == "__main__":
    test_hwinfo()
