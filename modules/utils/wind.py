import math
from typing import NamedTuple

import numpy as np

STANDARD_AIR_PRESSURE_HPA = 1013.25
STANDARD_AIR_TEMPERATURE_C = 15.0
DRY_AIR_GAS_CONSTANT = 287.058
STANDARD_GRAVITY = 9.80665


class SpeedImpact(NamedTuple):
    delta: float
    still_air_speed: float


class WindImpact(NamedTuple):
    headwind: float
    force_delta: float
    power_delta: float
    grade: float
    air_density: float


_NO_WIND_IMPACT = WindImpact(np.nan, np.nan, np.nan, np.nan, np.nan)
_NO_SPEED_IMPACT = SpeedImpact(np.nan, np.nan)


def get_wind_impact(
    speed,
    wind_speed,
    wind_direction,
    track,
    temperature,
    pressure,
    cda,
    total_weight,
):
    """Return the current aerodynamic impact relative to still air."""
    if (
        np.any(np.isnan((speed, wind_speed, wind_direction, track)))
        or speed <= 0
        or cda <= 0
        or total_weight <= 0
    ):
        return _NO_WIND_IMPACT

    relative_direction = math.radians(wind_direction - track)
    forward_wind = speed + math.cos(relative_direction) * wind_speed
    crosswind = math.sin(relative_direction) * wind_speed
    apparent_wind = math.hypot(forward_wind, crosswind)
    equivalent_wind = math.copysign(
        math.sqrt(abs(apparent_wind * forward_wind)), forward_wind
    )

    if np.isnan(temperature):
        temperature = STANDARD_AIR_TEMPERATURE_C
    if np.isnan(pressure):
        pressure = STANDARD_AIR_PRESSURE_HPA
    air_density = pressure * 100 / (DRY_AIR_GAS_CONSTANT * (temperature + 273.15))
    force_delta = 0.5 * air_density * cda * (apparent_wind * forward_wind - speed**2)
    return WindImpact(
        equivalent_wind - speed,
        force_delta,
        force_delta * speed,
        force_delta / (total_weight * STANDARD_GRAVITY) * 100,
        air_density,
    )


def get_wind_elevation(wind_work, total_weight):
    """Return accumulated wind work as equivalent elevation in metres."""
    if total_weight <= 0:
        return np.nan
    return wind_work / (total_weight * STANDARD_GRAVITY)


def _solve_still_air_speed(power, aero_factor, linear_force, current_speed):
    """Solve steady-state still-air speed for wheel-side power."""
    low = math.sqrt(max(-linear_force / (3 * aero_factor), 0.0))
    high = max(current_speed * 2, low * 2, 20.0)

    def required_power(speed):
        return aero_factor * speed**3 + linear_force * speed

    if required_power(low) > power:
        return np.nan
    while required_power(high) < power and high < 100:
        high *= 2
    if required_power(high) < power:
        return np.nan

    for _ in range(40):
        middle = (low + high) / 2
        if required_power(middle) < power:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def get_speed_impact(
    speed,
    force_delta,
    air_density,
    cda,
    total_weight,
    crr,
    grade_percent,
):
    """Return current speed difference from still air at equal modelled power."""
    if np.isnan(force_delta):
        return _NO_SPEED_IMPACT

    aero_factor = 0.5 * air_density * cda
    linear_force = total_weight * STANDARD_GRAVITY * (crr + grade_percent / 100)
    model_power = (aero_factor * speed**2 + linear_force + force_delta) * speed
    still_air_speed = _solve_still_air_speed(
        model_power,
        aero_factor,
        linear_force,
        speed,
    )
    if np.isnan(still_air_speed):
        return _NO_SPEED_IMPACT
    return SpeedImpact(speed - still_air_speed, still_air_speed)
