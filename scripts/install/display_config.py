"""Apply the Raspberry Pi display settings selected by install.sh."""

import argparse
import configparser
import os
import re
import stat
import tempfile
from io import StringIO
from pathlib import Path


BEGIN = "# BEGIN Pi Zero Bikecomputer display"
END = "# END Pi Zero Bikecomputer display"


def replace_file(path, content):
    mode = stat.S_IMODE(path.stat().st_mode)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        staged = Path(output.name)
        try:
            if stat.S_IMODE(os.fstat(output.fileno()).st_mode) != mode:
                os.fchmod(output.fileno(), mode)
            output.write(content)
            output.close()
            staged.replace(path)
        finally:
            staged.unlink(missing_ok=True)


def find_block(lines):
    markers = [
        (index, line.strip())
        for index, line in enumerate(lines)
        if line.strip() in (BEGIN, END)
    ]
    if not markers:
        return len(lines), len(lines)
    if [marker for _, marker in markers] != [BEGIN, END]:
        raise ValueError("Expected a single, complete Pi Zero Bikecomputer display block.")
    return markers[0][0], markers[1][0] + 1


def boot_entries(root, path, lines, visited):
    for number, line in lines:
        entry = line.partition("#")[0].strip()
        directive = entry.split(maxsplit=1)
        if len(directive) == 2 and directive[0] == "include":
            include = (root / directive[1]).resolve()
            if include in visited:
                continue
            visited.add(include)
            try:
                included = include.read_text(errors="surrogateescape")
            except FileNotFoundError:
                continue
            yield from boot_entries(
                root, include, enumerate(included.splitlines(), 1), visited
            )
        elif entry:
            yield path, number, entry


def overlay_conflicts(entry, profile, pwm):
    overlay = re.match(r"(?:dtoverlay|device_tree_overlay)\s*=\s*([^,\s]+)", entry)
    if not overlay:
        return False
    name = overlay[1]
    if pwm and name in {"pwm", "pwm-2chan", "pwm-ir-tx", "audremap"}:
        return True
    if name == "mip-pwm-backlight":
        return True
    if profile == "buzzer":
        return name == "sharp-drm" and bool(re.search(r",\s*backlight_", entry))
    return name in {
        "sharp-drm", "sitronix-touch", "spi-gpio35-39", "spi-gpio40-45"
    } or name.startswith("spi0-")


def overrides_managed_value(entry, options):
    key, _, value = entry.partition("=")
    if key.strip() == "max_framebuffers":
        return "max_framebuffers=0" in options and value.strip() != "0"
    if key.strip() in {"dtparam", "device_tree_param"}:
        for parameter in value.split(","):
            name, _, setting = parameter.partition("=")
            enabled = setting.strip() not in {"off", "false", "no", "0"}
            if name.strip() == "audio" and enabled and "dtparam=audio=off" in options:
                return True
            if name.strip() == "spi" and not enabled and "dtparam=spi=on" in options:
                return True
    return False


def render_boot_config(path, original, profile, options):
    lines = original.splitlines(keepends=True)
    start, end = find_block(lines)
    if profile == "buzzer" and any(
        line.startswith(("dtoverlay=sharp-drm,", "dtoverlay=spi0-1cs-inverted"))
        for line in lines[start:end]
    ):
        raise ValueError("Select the installed MIP profile and enable its PWM1 buzzer.")
    pwm = "dtparam=audio=off" in options
    found = []
    for first, last in ((0, start), (end, len(lines))):
        entries = boot_entries(
            path.parent, path, enumerate(lines[first:last], first + 1), {path.resolve()}
        )
        for source, number, entry in entries:
            if overlay_conflicts(entry, profile, pwm) or (
                first == end and overrides_managed_value(entry, options)
            ):
                found.append(f"{source}:{number}: {entry}")
    if found:
        raise ValueError(
            "Existing settings outside the installer block conflict with this selection.\n"
            "Review these lines before rerunning, or choose Keep existing display settings:\n"
            + "\n".join(found)
        )
    newline = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    before = "".join(lines[:start])
    if before and not before.endswith(("\n", "\r")):
        before += newline
    block = newline.join((BEGIN, "[all]", *options, END, ""))
    return before + block + "".join(lines[end:])


def configure_boot(path, profile, options, apply):
    current = path.read_bytes()
    updated = render_boot_config(
        path, current.decode("utf-8", "surrogateescape"), profile, options
    ).encode("utf-8", "surrogateescape")
    if not apply or current == updated:
        return

    backup = path.with_name(f"{path.name}.before-pizero-display")
    try:
        with backup.open("xb") as output:
            output.write(current)
    except FileExistsError:
        pass
    replace_file(path, updated)
    print(f"Display boot settings updated in {path}.")


def configure_settings(path, display, backlight):
    settings = configparser.ConfigParser(interpolation=None)
    with path.open() as source:
        settings.read_file(source)
    changed = False
    updates = [("GENERAL", "DISPLAY", display)]
    if settings.get("GENERAL", "BOARD", fallback="auto").strip().lower() == "auto":
        updates.append(("DISPLAY_PARAM", "USE_BACKLIGHT", str(backlight)))
    for section, key, value in updates:
        if not settings.has_section(section):
            settings.add_section(section)
        if settings.get(section, key, fallback=None) != value:
            settings.set(section, key, value)
            changed = True
    if changed:
        output = StringIO()
        settings.write(output)
        replace_file(path, output.getvalue().encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    boot = subparsers.add_parser("boot")
    boot.add_argument("--apply", action="store_true")
    boot.add_argument("path", type=Path)
    boot.add_argument("profile", choices=("drm", "spidev", "buzzer"))
    boot.add_argument("options", nargs="+")
    settings = subparsers.add_parser("settings")
    settings.add_argument("path", type=Path)
    settings.add_argument("display")
    settings.add_argument("backlight", choices=("true", "false"))
    args = parser.parse_args()

    try:
        if args.action == "settings":
            configure_settings(args.path, args.display, args.backlight == "true")
        else:
            configure_boot(args.path, args.profile, args.options, args.apply)
    except (OSError, ValueError, configparser.Error) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
