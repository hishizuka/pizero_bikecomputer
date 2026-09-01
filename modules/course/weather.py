import asyncio
from datetime import datetime, timedelta, timezone

import numpy as np


class CourseWeatherService:
    @staticmethod
    async def fetch(course):
        config = course.config
        course_indices = []
        timeline = []
        current_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        index = max(course.index.value, 0)
        course_indices.append(index)
        timeline.append(current_time)

        distance = int(course.index.distance / 1000) + config.G_GROSS_AVE_SPEED
        while distance < course.distance[-1]:
            index += np.argmin(np.abs(course.distance[index:] - distance))
            course_indices.append(index)
            current_time += timedelta(hours=1)
            timeline.append(current_time)
            distance += config.G_GROSS_AVE_SPEED

        rest_distance = int(course.distance[-1] % config.G_GROSS_AVE_SPEED)
        if rest_distance and rest_distance / config.G_GROSS_AVE_SPEED > 0.5:
            course_indices.append(len(course.longitude) - 1)
            current_time += timedelta(hours=rest_distance / config.G_GROSS_AVE_SPEED)
            timeline.append(current_time)

        weather = {
            key: [np.nan] * len(course_indices)
            for key in (
                "wind_speed",
                "wind_direction",
                "temperature",
                "precipitation",
                "cloud_cover",
            )
        }
        loaded = [False] * len(course_indices)
        retry_delays = (1.0, 3.0, 8.0)

        for attempt in range(len(retry_delays) + 1):
            for i, course_index in enumerate(course_indices):
                if loaded[i]:
                    continue
                result = await config.api.get_course_weather(
                    [course.longitude[course_index], course.latitude[course_index]],
                    timeline[i],
                )
                if result is None:
                    continue
                for key in weather:
                    weather[key][i] = result[key]
                loaded[i] = True

            if all(loaded):
                break
            if attempt < len(retry_delays):
                await asyncio.sleep(retry_delays[attempt])

        return {
            "course_indices": course_indices,
            "timeline": timeline,
            **weather,
        }
