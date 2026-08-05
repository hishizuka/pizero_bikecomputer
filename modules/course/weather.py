import asyncio
from datetime import datetime, timedelta, timezone

import numpy as np


class CourseWeatherService:
    @staticmethod
    async def fetch(course):
        config = course.config
        coordinates = []
        timeline = []
        current_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        index = max(course.index.value, 0)
        coordinates.append([course.longitude[index], course.latitude[index]])
        timeline.append(current_time)

        distance = int(course.index.distance / 1000) + config.G_GROSS_AVE_SPEED
        while distance < course.distance[-1]:
            index += np.argmin(np.abs(course.distance[index:] - distance))
            coordinates.append([course.longitude[index], course.latitude[index]])
            current_time += timedelta(hours=1)
            timeline.append(current_time)
            distance += config.G_GROSS_AVE_SPEED

        rest_distance = int(course.distance[-1] % config.G_GROSS_AVE_SPEED)
        if rest_distance and rest_distance / config.G_GROSS_AVE_SPEED > 0.5:
            coordinates.append([course.longitude[-1], course.latitude[-1]])
            current_time += timedelta(hours=rest_distance / config.G_GROSS_AVE_SPEED)
            timeline.append(current_time)

        wind_speed = [np.nan] * len(coordinates)
        wind_direction = [np.nan] * len(coordinates)
        retry_delays = (1.0, 3.0, 8.0)

        for attempt in range(len(retry_delays) + 1):
            for i, coordinate in enumerate(coordinates):
                if not any(np.isnan((wind_speed[i], wind_direction[i]))):
                    continue
                speed, direction, _, _ = await config.api.get_wind(
                    coordinate, forecast_time=timeline[i]
                )
                if not any(np.isnan((speed, direction))):
                    wind_speed[i] = float(speed)
                    wind_direction[i] = float(direction)

            if not any(np.isnan(wind_speed)) and not any(np.isnan(wind_direction)):
                break
            if attempt < len(retry_delays):
                await asyncio.sleep(retry_delays[attempt])

        return coordinates, timeline, wind_speed, wind_direction
