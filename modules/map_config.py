from datetime import datetime


def add_map_config(config):

    # toner is deleted because API key is now needed.
    # config.G_MAP_CONFIG["toner"] = {
    #     "url": "https://tiles.stadiamaps.com/tiles/stamen_toner/{z}/{x}/{y}.png?api_key=YOUR_API_KEY"
    #     "attribution": "Map tiles by Stamen Design, under CC BY 3.0.<br />Data by OpenStreetMap, under ODbL",
    #     "tile_size": 256,
    # }

    config.G_MAP_CONFIG["openstreetmap"] = {
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "© OpenStreetMap contributors",
        "tile_size": 256,
        "user_agent": True,
    }
    config.G_MAP_CONFIG["wikimedia"] = {
        "url": "https://maps.wikimedia.org/osm-intl/{z}/{x}/{y}.png?lang=en",  # G_LANG: en/ja
        "attribution": "© OpenStreetMap contributors",
        "referer": "https://commons.wikimedia.org/wiki/",
        "tile_size": 256,
        "user_agent": True,
    }
    config.G_MAP_CONFIG["wikimedia_2x"] = {
        "url": "https://maps.wikimedia.org/osm-intl/{z}/{x}/{y}@2x.png?lang=en",  # G_LANG: en/ja
        "attribution": "© OpenStreetMap contributors",
        "referer": "https://commons.wikimedia.org/wiki/",
        "tile_size": 512,
        "user_agent": True,
    }
    # japanese tile
    config.G_MAP_CONFIG["jpn_kokudo_chiri_in"] = {
        "url": "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png",
        "attribution": "国土地理院",
        "tile_size": 256,
    }

    config.G_HEATMAP_OVERLAY_MAP_CONFIG["rwg_heatmap"] = {
        # start_color: low, white(FFFFFF) is recommended.
        # end_color: high, any color you like.
        "url": "https://heatmap.ridewithgps.com/normalized/{z}/{x}/{y}.png?start_color=%23FFFFFF&end_color=%23FF8800",
        "attribution": "Ride with GPS",
        "tile_size": 256,
        "max_zoomlevel": 16,
        "min_zoomlevel": 10,
    }
    # strava heatmap
    # https://wiki.openstreetmap.org/wiki/Strava
    # bluered / hot / blue / purple / gray
    config.G_HEATMAP_OVERLAY_MAP_CONFIG["strava_heatmap_bluered"] = {
        "url": "https://heatmap-external-b.strava.com/tiles-auth/ride/bluered/{z}/{x}/{y}.png?px=256&Key-Pair-Id={key_pair_id}&Policy={policy}&Signature={signature}",
        "attribution": "STRAVA",
        "tile_size": 256,
        "max_zoomlevel": 16,
        "min_zoomlevel": 10,
    }
    config.G_HEATMAP_OVERLAY_MAP_CONFIG["strava_heatmap_hot"] = {
        "url": "https://heatmap-external-b.strava.com/tiles-auth/ride/hot/{z}/{x}/{y}.png?px=256&Key-Pair-Id={key_pair_id}&Policy={policy}&Signature={signature}",
        "attribution": "STRAVA",
        "tile_size": 256,
        "max_zoomlevel": 16,
        "min_zoomlevel": 10,
    }
    config.G_HEATMAP_OVERLAY_MAP_CONFIG["strava_heatmap_blue"] = {
        "url": "https://heatmap-external-b.strava.com/tiles-auth/ride/blue/{z}/{x}/{y}.png?px=256&Key-Pair-Id={key_pair_id}&Policy={policy}&Signature={signature}",
        "attribution": "STRAVA",
        "tile_size": 256,
        "max_zoomlevel": 16,
        "min_zoomlevel": 10,
    }
    config.G_HEATMAP_OVERLAY_MAP_CONFIG["strava_heatmap_purple"] = {
        "url": "https://heatmap-external-b.strava.com/tiles-auth/ride/purple/{z}/{x}/{y}.png?px=256&Key-Pair-Id={key_pair_id}&Policy={policy}&Signature={signature}",
        "attribution": "STRAVA",
        "tile_size": 256,
        "max_zoomlevel": 16,
        "min_zoomlevel": 10,
    }
    config.G_HEATMAP_OVERLAY_MAP_CONFIG["strava_heatmap_gray"] = {
        "url": "https://heatmap-external-b.strava.com/tiles-auth/ride/gray/{z}/{x}/{y}.png?px=256&Key-Pair-Id={key_pair_id}&Policy={policy}&Signature={signature}",
        "attribution": "STRAVA",
        "tile_size": 256,
        "max_zoomlevel": 16,
        "min_zoomlevel": 10,
    }

    # worldwide rain tile
    config.G_RAIN_OVERLAY_MAP_CONFIG["rainviewer"] = {
        "url": "https://tilecache.rainviewer.com/v2/radar/{validtime}/256/{z}/{x}/{y}/6/1_1.png",
        "attribution": "RainViewer",
        "tile_size": 256,
        "max_zoomlevel": 18,
        "min_zoomlevel": 1,
        "time_list": "https://api.rainviewer.com/public/weather-maps.json",
        "current_time": None,
        "current_time_func": datetime.now,  # local?
        "basetime": None,
        "validtime": None,
        "time_interval": 10,  # [minutes]
        "update_minutes": 1,  # typically int(time_interval/2) [minutes]
        "max_validtime": 0,  # [minutes]
        "min_validtime": -120,  # [minutes]
        "time_format": "unix_timestamp",
    }
    # japanese rain tile
    config.G_RAIN_OVERLAY_MAP_CONFIG["jpn_jma_bousai"] = {
        "url": "https://www.jma.go.jp/bosai/jmatile/data/nowc/{basetime}/none/{validtime}/surf/hrpns/{z}/{x}/{y}.png",
        "attribution": "Japan Meteorological Agency",
        "tile_size": 256,
        "max_zoomlevel": 10,
        "min_zoomlevel": 4,
        "past_time_list": "https://www.jma.go.jp/bosai/jmatile/data/nowc/targetTimes_N1.json",
        "forcast_time_list": "https://www.jma.go.jp/bosai/jmatile/data/nowc/targetTimes_N2.json",
        "current_time": None,
        "current_time_func": datetime.utcnow,
        "basetime": None,
        "validtime": None,
        "time_interval": 5,  # [minutes]
        "update_minutes": 1,  # [minutes]
        "max_validtime": 60,  # [minutes]
        "min_validtime": -180,  # [minutes]
        "time_format": "%Y%m%d%H%M%S",
    }

    # worldwide wind tile
    # https://weather.openportguide.de/index.php/en/weather-forecasts/weather-tiles
    config.G_WIND_OVERLAY_MAP_CONFIG["openportguide"] = {
        "url": "https://weather.openportguide.de/tiles/actual/wind_stream/0h/{z}/{x}/{y}.png",
        "attribution": "openportguide",
        "tile_size": 256,
        "max_zoomlevel": 7,
        "min_zoomlevel": 0,
        "current_time": None,
        "current_time_func": datetime.utcnow,
        "basetime": None,
        "validtime": None,
        "time_interval": 60,  # [minutes]
        "update_minutes": 0,  # [minutes]
        "max_validtime": 0,  # [minutes]  # 6h, 12h, 24h, 36h, 48h, 60h, 72h. not suitable for cycling.
        "min_validtime": 0,  # [minutes]
        "time_format": "%H%MZ%d%b%Y",
    }
    # japanese wind tile
    config.G_WIND_OVERLAY_MAP_CONFIG["jpn_scw"] = {
        "url": "https://{subdomain}.supercweather.com/tl/msm/{basetime}/{validtime}/wa/{z}/{x}/{y}.png",
        "attribution": "SCW",
        "tile_size": 256,
        "max_zoomlevel": 8,
        "min_zoomlevel": 8,
        "inittime": "https://k2.supercweather.com/tl/msm/initime.json?rand={rand}",
        "fl": "https://k2.supercweather.com/tl/msm/{basetime}/fl.json?rand={rand}",
        "current_time": None,
        "current_time_func": datetime.utcnow,
        "timeline": None,
        "timeline_update_date": None,
        "basetime": None,
        "validtime": None,
        "subdomain": None,
        "time_interval": 60,  # [minutes]
        "update_minutes": 0,  # [minutes]
        "time_format": "%H%MZ%d%b%Y",  # need upper()
        "referer": "https://supercweather.com/",
    }

    # worldwide DEM(Digital Elevation Model) map
    # Mapbox Terrain-DEM v1
    config.G_DEM_MAP_CONFIG["mapbox_terrain_rgb"] = {
        "url": "https://api.mapbox.com/v4/mapbox.terrain-rgb/{z}/{x}/{y}.pngraw?access_token=YOUR_MAPBOX_ACCESS_TOKEN",
        "attribution": "© Mapbox, © OpenStreetMap",
        "fix_zoomlevel": 15,
        "tile_size": 256,
    }

    # japanese DEM(Digital Elevation Model) map
    config.G_DEM_MAP_CONFIG["jpn_kokudo_chiri_in_DEM"] = {
        "url": "https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{z}/{x}/{y}.png",  # DEM5A(zoom: 1-15)
        "attribution": "国土地理院",
        "fix_zoomlevel": 15,
        "tile_size": 256,
        "retry_url": "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png",  # DEM10B(zoom: 1-14)
        "retry_zoomlevel": 14,
    }
