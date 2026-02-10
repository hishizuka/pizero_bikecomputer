import os
import pickle
import tempfile
from datetime import datetime, timezone


# store temporary values. unreadable and uneditable.
class AppState:
    interval = 20  # [s]

    pickle_file = "state.pickle"

    def __init__(self):
        self.last_write_time = datetime.now(timezone.utc)
        self.values = {}

        try:
            with open(self.pickle_file, "rb") as f:
                self.values = pickle.load(f)
        except FileNotFoundError:
            self.values = {}
        except (
            EOFError,
            OSError,
            pickle.UnpicklingError,
            AttributeError,
            ValueError,
            TypeError,
        ) as exc:
            self.values = {}
            self._backup_corrupted_state_file(exc)

    def write(self):
        directory = os.path.dirname(self.pickle_file) or "."
        fd, tmp_path = tempfile.mkstemp(
            prefix=".state.",
            suffix=".tmp",
            dir=directory,
        )
        try:
            with os.fdopen(fd, "wb") as f:
                pickle.dump(self.values, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.pickle_file)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _backup_corrupted_state_file(self, exc):
        if not os.path.exists(self.pickle_file):
            return

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = f"{self.pickle_file}.corrupt-{timestamp}"
        suffix = 1
        while os.path.exists(backup_path):
            backup_path = f"{self.pickle_file}.corrupt-{timestamp}-{suffix}"
            suffix += 1

        try:
            os.replace(self.pickle_file, backup_path)
        except OSError as backup_exc:
            return


    def set_value(self, key, value, force_apply=False):
        self.values[key] = value

        now = datetime.now(timezone.utc)

        if (
            not force_apply
            and (now - self.last_write_time).total_seconds() < self.interval
        ):
            return

        self.write()
        self.last_write_time = now

    def get_value(self, key, default_value):
        return self.values.get(key, default_value)

    # stored variables:
    #  G_MANUAL_STATUS
    #  garmin_session
    #  mag_min, mag_max, sealevel_pa, sealevel_temp
    #  pos_lon, pos_lat
    #  ant+_sc_values, ant+_spd_values, ant+_power_values_16, ant+_power_values_17, ant+_power_values_18

    # reset
    def reset(self):
        for k, v in list(self.values.items()):
            if k.startswith(("G_MANUAL_STATUS", "sealevel_", "ant+_")):
                del self.values[k]
        self.write()

    # quit (power_off)
    def delete(self):
        for k, v in list(self.values.items()):
            if k.startswith("ant+_"):
                del self.values[k]
        self.write()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--delete")
    parser.add_argument("-r", "--reset", action="store_true", default=False)
    args = parser.parse_args()

    s = AppState()

    if args.delete:
        del_key = args.delete
    else:
        del_key = None
    if args.reset:
        s.reset()
    elif del_key is not None and del_key in s.values:
        print(f"delete {del_key}")
        del s.values[del_key]
        s.write()

    print(s.values)
