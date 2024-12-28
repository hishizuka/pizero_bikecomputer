import pickle
from datetime import datetime, timezone


# store temporary values. unreadable and uneditable.
class AppState:
    interval = 20  # [s]

    last_write_time = datetime.now(timezone.utc)
    pickle_file = "state.pickle"
    values = None

    def __init__(self):
        try:
            with open(self.pickle_file, "rb") as f:
                self.values = pickle.load(f)
        except FileNotFoundError:
            self.values = {}

    def set_value(self, key, value, force_apply=False):
        self.values[key] = value

        now = datetime.now(timezone.utc)

        if (
            not force_apply
            and (now - self.last_write_time).total_seconds() < self.interval
        ):
            return

        with open(self.pickle_file, "wb") as f:
            pickle.dump(self.values, f)
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
        with open(self.pickle_file, "wb") as f:
            pickle.dump(self.values, f)

    # quit (power_off)
    def delete(self):
        for k, v in list(self.values.items()):
            if k.startswith("ant+_"):
                del self.values[k]
        with open(self.pickle_file, "wb") as f:
            pickle.dump(self.values, f)
