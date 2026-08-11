import math


def round_half_away_from_zero(value):
    return int(math.copysign(math.floor(abs(value) + 0.5), value))
