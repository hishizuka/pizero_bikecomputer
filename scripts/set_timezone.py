import sys
import subprocess


argv = sys.argv
if len(argv) != 3:
    print(argv, len(argv))
    exit()

lat = None
lon = None

try:
    lat = float(argv[1])
    lon = float(argv[2])
except Exception as e:
    print(e)
    exit()

try:
    from timezonefinder import TimezoneFinder
except Exception as e:
    print(e)
    exit()

tz = TimezoneFinder()

try:
    tz_str = tz.timezone_at(lng=lon, lat=lat)

    if tz_str is None:
        # tz_str = tz.certain_timezone_at(lng=lon, lat=lat)
        tz_str = tz.closest_timezone_at(lng=lon, lat=lat)

    print(tz_str)

    if tz_str is not None:
        cmd = [
            "sudo",
            "timedatectl",
            "set-timezone",
            tz_str,
        ]
        print(cmd)
        try:
            subprocess.run(cmd)
        except:
            subprocess.call(cmd)
except Exception as e:
    print(e)
