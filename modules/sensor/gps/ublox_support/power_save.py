POWER_MODE_FULL_POWER = 0
POWER_MODE_LOW_POWER = 2
STATE_RECEIVER_MODEL = "ublox_receiver_model"


def normalized_receiver_model(model):
    return (model or "").upper().replace("-", "")


def low_power_config_for_receiver(model):
    normalized_model = normalized_receiver_model(model)
    if "MAXM10N" in normalized_model:
        return "leap", [
            ("CFG_TP_TP1_ENA", 0),
            ("CFG_RATE_NAV", 1),
            ("CFG_PM_OPERATEMODE", POWER_MODE_LOW_POWER),
        ]
    if "MAXM10S" in normalized_model:
        return "psmct", [
            ("CFG_RATE_MEAS", 1000),
            ("CFG_RATE_NAV", 1),
            ("CFG_SIGNAL_SBAS_ENA", 0),
            ("CFG_SIGNAL_SBAS_L1CA_ENA", 0),
            ("CFG_SIGNAL_BDS_B1C_ENA", 0),
            ("CFG_PM_UPDATEEPH", 1),
            ("CFG_PM_OPERATEMODE", POWER_MODE_LOW_POWER),
        ]
    return None, []


def full_power_config():
    return [("CFG_PM_OPERATEMODE", POWER_MODE_FULL_POWER)]
