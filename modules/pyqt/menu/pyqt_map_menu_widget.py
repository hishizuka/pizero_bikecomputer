import asyncio

from .pyqt_menu_widget import MenuWidget, ListWidget


class MapMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # MenuConfig Key, Name(page_name), button_attribute, connected functions, layout
            ("SELECT_MAP", "Select Map", "submenu", self.select_map),
            ("MAP_OVERLAY", "Map Overlay", "submenu", self.map_overlay),
            ("EXTERNAL_DATA_SOURCES", "External Data Sources", "submenu", self.external_data_sources),
        )
        self.add_buttons(button_conf)

    def select_map(self):
        self.change_page("Select Map", preprocess=True)

    def map_overlay(self):
        self.change_page("Map Overlay")
    
    def external_data_sources(self):
        self.change_page("External Data Sources")


class MapListWidget(ListWidget):
    def __init__(self, parent, page_name, config):
        # keys are used for item label
        self.settings = config.G_MAP_CONFIG
        super().__init__(parent=parent, page_name=page_name, config=config)

    def get_default_value(self):
        return self.config.G_MAP

    async def button_func_extra(self):
        self.config.G_MAP = self.selected_item.title_label.text()
        # reset map
        self.config.check_map_dir()
        self.config.gui.map_widget.reset_map()


class MapOverlayMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # MenuConfig Key, Name(page_name), button_attribute, connected functions, layout
            ("HEATMAP", "Heatmap", "toggle", lambda: self.onoff_heatmap(True)),
            ("HEATMAP_LIST", "Heatmap List", "submenu", self.select_heatmap),
            ("RAIN_MAP", "Rain map", "toggle", lambda: self.onoff_rainmap(True)),
            ("RAIN_MAP_LIST", "Rain map List", "submenu", self.select_rainmap),
            ("WIND_MAP", "Wind map", "toggle", lambda: self.onoff_windmap(True)),
            ("WIND_MAP_LIST", "Wind map List", "submenu", self.select_windmap),
        )
        self.add_buttons(button_conf)

        self.onoff_heatmap(False)
        self.onoff_rainmap(False)
        self.onoff_windmap(False)

    def onoff_heatmap(self, change=True):
        self.onoff_map("HEATMAP", change, self.config.G_USE_HEATMAP_OVERLAY_MAP)

    def onoff_rainmap(self, change=True):
        self.onoff_map("RAIN_MAP", change, self.config.G_USE_RAIN_OVERLAY_MAP)

    def onoff_windmap(self, change=True):
        self.onoff_map("WIND_MAP", change, self.config.G_USE_WIND_OVERLAY_MAP)

    def onoff_map(self, overlay_type, change, is_use):
        status = is_use
        list_key = overlay_type + "_LIST"
        if change:
            if overlay_type == "HEATMAP":
                self.config.G_USE_HEATMAP_OVERLAY_MAP = not status
            elif overlay_type == "RAIN_MAP":
                self.config.G_USE_RAIN_OVERLAY_MAP = not status
            elif overlay_type == "WIND_MAP":
                self.config.G_USE_WIND_OVERLAY_MAP = not status
            status = not status
            if self.config.display.has_touch:
                self.config.gui.map_widget.enable_overlay_button()

        self.buttons.change_toggle_if_exists(overlay_type, status)

        # toggle list
        self.buttons.onoff_button_if_exists(list_key, status)

        if (
            not self.config.G_USE_HEATMAP_OVERLAY_MAP
            and not self.config.G_USE_RAIN_OVERLAY_MAP
            and not self.config.G_USE_WIND_OVERLAY_MAP
            and self.config.gui.map_widget is not None
        ):
            self.config.gui.map_widget.remove_overlay()

    def select_heatmap(self):
        self.change_page("Heatmap List", preprocess=True)

    def select_rainmap(self):
        self.change_page("Rain map List", preprocess=True)

    def select_windmap(self):
        self.change_page("Wind map List", preprocess=True)


class HeatmapListWidget(ListWidget):
    def __init__(self, parent, page_name, config):
        # keys are used for item label
        self.settings = config.G_HEATMAP_OVERLAY_MAP_CONFIG
        super().__init__(parent=parent, page_name=page_name, config=config)

    def get_default_value(self):
        return self.config.G_HEATMAP_OVERLAY_MAP

    async def button_func_extra(self):
        self.config.G_HEATMAP_OVERLAY_MAP = self.selected_item.title_label.text()
        # reset map
        self.config.check_map_dir()
        self.config.gui.map_widget.reset_map()
        # update strava cookie
        if "strava_heatmap" in self.config.G_HEATMAP_OVERLAY_MAP:
            asyncio.get_running_loop().run_in_executor(
                None, self.config.api.get_strava_cookie
            )


class RainmapListWidget(ListWidget):
    def __init__(self, parent, page_name, config):
        # keys are used for item label
        self.settings = config.G_RAIN_OVERLAY_MAP_CONFIG
        super().__init__(parent=parent, page_name=page_name, config=config)

    def get_default_value(self):
        return self.config.G_RAIN_OVERLAY_MAP

    async def button_func_extra(self):
        self.config.G_RAIN_OVERLAY_MAP = self.selected_item.title_label.text()
        # reset map
        self.config.check_map_dir()
        self.config.gui.map_widget.reset_map()


class WindmapListWidget(ListWidget):
    def __init__(self, parent, page_name, config):
        # keys are used for item label
        self.settings = config.G_WIND_OVERLAY_MAP_CONFIG
        super().__init__(parent=parent, page_name=page_name, config=config)

    def get_default_value(self):
        return self.config.G_WIND_OVERLAY_MAP

    async def button_func_extra(self):
        self.config.G_WIND_OVERLAY_MAP = self.selected_item.title_label.text()
        # reset map
        self.config.check_map_dir()
        self.config.gui.map_widget.reset_map()


class ExternalDataSourceMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # MenuConfig Key, Name(page_name), button_attribute, connected functions, layout
            ("WIND", "Wind", "toggle", lambda: self.onoff_wind(True)),
            ("WIND_SOURCE", "Wind Source", "submenu", self.select_wind_source),
            ("DEM_TILE", "DEM Tile", "toggle", lambda: self.onoff_dem_tile(True)),
            ("DEM_TILE_SOURCE", "DEM Tile source", "submenu", self.select_dem_tile),
        )
        self.add_buttons(button_conf)

        self.onoff_wind(False)
        self.onoff_dem_tile(False)

    def onoff_wind(self, change=True):
        if change:
            self.config.G_USE_WIND_DATA_SOURCE = not self.config.G_USE_WIND_DATA_SOURCE
        self.buttons.change_toggle_if_exists("WIND", self.config.G_USE_WIND_DATA_SOURCE)
        self.buttons.onoff_button_if_exists("WIND_SOURCE", self.config.G_USE_WIND_DATA_SOURCE)

    def onoff_dem_tile(self, change=True):
        if change:
            self.config.G_USE_DEM_TILE = not self.config.G_USE_DEM_TILE
        self.buttons.change_toggle_if_exists("DEM_TILE", self.config.G_USE_DEM_TILE)
        self.buttons.onoff_button_if_exists("DEM_TILE_SOURCE", self.config.G_USE_DEM_TILE)

    def select_wind_source(self):
        self.change_page("Wind Source", preprocess=True)
        
    def select_dem_tile(self):
        self.change_page("DEM Tile source", preprocess=True)
        

class WindSourceListWidget(ListWidget):
    def __init__(self, parent, page_name, config):
        # keys are used for item label
        self.settings = {
            "openmeteo": None
        }
        for k in config.G_WIND_OVERLAY_MAP_CONFIG:
            if k.startswith("jpn_scw"):
                self.settings[k] = config.G_WIND_OVERLAY_MAP_CONFIG[k]
            
        super().__init__(parent=parent, page_name=page_name, config=config)

    def get_default_value(self):
        return self.config.G_WIND_DATA_SOURCE

    async def button_func_extra(self):
        self.config.G_WIND_DATA_SOURCE = self.selected_item.title_label.text()
        # reset map
        self.config.check_map_dir()


class DEMTileListWidget(ListWidget):
    def __init__(self, parent, page_name, config):
        # keys are used for item label
        self.settings = config.G_DEM_MAP_CONFIG
        super().__init__(parent=parent, page_name=page_name, config=config)

    def get_default_value(self):
        return self.config.G_DEM_MAP

    async def button_func_extra(self):
        self.config.G_DEM_MAP = self.selected_item.title_label.text()
        # reset map
        self.config.check_map_dir()
