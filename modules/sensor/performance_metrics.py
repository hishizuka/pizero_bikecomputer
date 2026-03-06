import numpy as np


NP_WINDOW_SIZE_DEFAULT = 30


def reset_performance_metrics_state(sensor):
    integrated = sensor.values["integrated"]
    integrated["normalized_power"] = np.nan
    integrated["w_prime_balance"] = sensor.config.G_POWER_W_PRIME
    integrated["w_prime_power_sum"] = 0
    integrated["w_prime_power_count"] = 0
    integrated["w_prime_t"] = 0
    integrated["w_prime_sum"] = 0
    integrated["pwr_mean_under_cp"] = 0
    integrated["tau"] = 546 * np.exp(-0.01 * (sensor.config.G_POWER_CP - 0)) + 316
    integrated["tss"] = 0.0

    sensor.np_window_size = getattr(sensor, "NP_WINDOW_SIZE", NP_WINDOW_SIZE_DEFAULT)
    sensor.np_window_30s = []
    sensor.np_window_sum = 0.0
    sensor.np_sum_ma4 = 0.0
    sensor.np_count_ma4 = 0


def update_normalized_power(sensor, pwr):
    if sensor.config.G_STOPWATCH_STATUS != "START":
        return
    if np.isnan(pwr):
        return

    window_size = sensor.np_window_size
    np_power = max(float(pwr), 0.0)
    if len(sensor.np_window_30s) < window_size:
        sensor.np_window_30s.append(np_power)
        sensor.np_window_sum += np_power
    else:
        sensor.np_window_sum += np_power - sensor.np_window_30s[0]
        sensor._shift_window_and_append(sensor.np_window_30s, np_power)

    if len(sensor.np_window_30s) >= window_size:
        np_ma30 = sensor.np_window_sum / window_size
        sensor.np_sum_ma4 += np_ma30**4
        sensor.np_count_ma4 += 1
        sensor.values["integrated"]["normalized_power"] = (
            sensor.np_sum_ma4 / sensor.np_count_ma4
        ) ** 0.25


def calc_w_prime_balance(sensor, pwr):
    # https://medium.com/critical-powers/comparison-of-wbalance-algorithms-8838173e2c15
    integrated = sensor.values["integrated"]
    dt = sensor.config.G_SENSOR_INTERVAL
    pwr_cp_diff = pwr - sensor.config.G_POWER_CP

    # Waterworth algorithm
    if sensor.config.G_POWER_W_PRIME_ALGORITHM == "WATERWORTH":
        if pwr < sensor.config.G_POWER_CP:
            integrated["w_prime_power_sum"] = integrated["w_prime_power_sum"] + pwr
            integrated["w_prime_power_count"] = integrated["w_prime_power_count"] + 1
            integrated["pwr_mean_under_cp"] = (
                integrated["w_prime_power_sum"] / integrated["w_prime_power_count"]
            )
            tau_new = (
                546
                * np.exp(
                    -0.01
                    * (sensor.config.G_POWER_CP - integrated["pwr_mean_under_cp"])
                )
                + 316
            )
            # When tau changes, rescale w_prime_sum so W'balance is continuous.
            # W'bal = W' - w_prime_sum * exp(-t/tau) must be preserved.
            if tau_new != integrated["tau"] and integrated["w_prime_t"] > 0:
                w_bal = (
                    sensor.config.G_POWER_W_PRIME
                    - integrated["w_prime_sum"]
                    * np.exp(-integrated["w_prime_t"] / integrated["tau"])
                )
                integrated["w_prime_sum"] = (
                    sensor.config.G_POWER_W_PRIME - w_bal
                ) * np.exp(integrated["w_prime_t"] / tau_new)
            integrated["tau"] = tau_new

        # Accumulate: (P-CP)+ * exp(t/tau) * dt [J scaled for later exp(-T/tau)]
        integrated["w_prime_sum"] += (
            max(0, pwr_cp_diff) * dt * np.exp(integrated["w_prime_t"] / integrated["tau"])
        )
        integrated["w_prime_t"] += dt
        integrated["w_prime_balance"] = (
            sensor.config.G_POWER_W_PRIME
            - integrated["w_prime_sum"] * np.exp(-integrated["w_prime_t"] / integrated["tau"])
        )

    # Differential algorithm
    elif sensor.config.G_POWER_W_PRIME_ALGORITHM == "DIFFERENTIAL":
        cp_pwr_diff = -pwr_cp_diff
        if cp_pwr_diff < 0:
            # consume (P > CP): deplete proportional to excess power and time
            integrated["w_prime_balance"] += cp_pwr_diff * dt
        else:
            # recovery (P < CP): recover toward W' with exponential approach
            integrated["w_prime_balance"] += (
                cp_pwr_diff
                * (sensor.config.G_POWER_W_PRIME - integrated["w_prime_balance"])
                / sensor.config.G_POWER_W_PRIME
                * dt
            )

    # Clamp to [0, W']: balance cannot exceed full charge or go physically undefined
    integrated["w_prime_balance"] = min(
        max(integrated["w_prime_balance"], 0), sensor.config.G_POWER_W_PRIME
    )
    integrated["w_prime_balance_normalized"] = round(
        integrated["w_prime_balance"] / sensor.config.G_POWER_W_PRIME * 100,
        1,
    )


def calc_form_metrics(sensor, pwr):
    """Compute TSS each sensor interval.

    TSS (Training Stress Score):
        Incremental approximation: (P/CP)^2 * dt/3600 * 100 per second.
        Uses CP as a proxy for FTP.
    """
    if not np.isnan(pwr) and pwr > 0:
        cp = sensor.config.G_POWER_CP
        dt = sensor.config.G_SENSOR_INTERVAL
        sensor.values["integrated"]["tss"] += (pwr / cp) ** 2 * dt / 3600 * 100
