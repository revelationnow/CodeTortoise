"""Query a (vendor) compiler driver for implicit include dirs, predefined macros, resource dir.

Same idea as clangd's --query-driver: lets an upstream libclang parse code meant for a
vendor cross toolchain.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

_TARGET_PREFIXES = ("--target=", "--sysroot", "-isysroot", "-march=", "-mcpu=", "-mfpu=",
                    "-mfloat-abi=", "-mabi=", "-mtune=", "-std=", "-stdlib=")
_TARGET_EXACT = {"-m32", "-m64", "-mthumb", "-marm", "-mbig-endian", "-mlittle-endian"}
_TARGET_WITH_VALUE = {"-target", "--sysroot", "-isysroot"}


@dataclass(frozen=True)
class DriverInfo:
    include_dirs: tuple[str, ...]
    defines: tuple[tuple[str, str], ...]
    resource_dir: str | None


def target_flags(args: list[str]) -> list[str]:
    """Subset of sanitized args that affects the driver's implicit includes/macros."""
    out = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in _TARGET_WITH_VALUE and i + 1 < len(args):
            out += [a, args[i + 1]]
            i += 2
            continue
        if a in _TARGET_EXACT or a.startswith(_TARGET_PREFIXES):
            out.append(a)
        i += 1
    return out


def parse_driver_output(stdout: str, stderr: str) -> tuple[list[str], list[tuple[str, str]]]:
    dirs: list[str] = []
    in_list = False
    for line in stderr.splitlines():
        if line.startswith("#include <...> search starts here:") or line.startswith('#include "..." search starts here:'):
            in_list = True
            continue
        if line.startswith("End of search list."):
            in_list = False
            continue
        if in_list and line.startswith(" "):
            d = line.strip().removesuffix(" (framework directory)")
            if d not in dirs:
                dirs.append(d)
    defines = []
    for line in stdout.splitlines():
        if line.startswith("#define "):
            _, _, rest = line.partition(" ")
            name, _, value = rest.partition(" ")
            defines.append((name, value))
    return dirs, defines


def query_driver(driver: str, target_args: list[str], lang: str, timeout: float = 60) -> DriverInfo:
    """lang: 'c' or 'c++'. Raises RuntimeError if the driver cannot be run."""
    try:
        r = subprocess.run([driver, *target_args, "-E", "-dM", "-v", "-x", lang, "/dev/null"],
                           capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"driver query failed: {e}") from e
    if r.returncode != 0:
        raise RuntimeError(f"driver query failed: {r.stderr.strip()[-500:]}")
    dirs, defines = parse_driver_output(r.stdout, r.stderr)
    resource_dir = None
    try:
        rr = subprocess.run([driver, *target_args, "-print-resource-dir"], capture_output=True,
                            text=True, timeout=timeout)
        if rr.returncode == 0 and rr.stdout.strip():
            resource_dir = rr.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return DriverInfo(tuple(dirs), tuple(defines), resource_dir)
