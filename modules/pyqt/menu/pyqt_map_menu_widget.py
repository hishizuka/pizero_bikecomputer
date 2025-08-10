import asyncio

from .pyqt_menu_widget import MenuWidget, ListWidget


class MapMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("Select Map", "submenu", self.select_map),
            ("Map Overlay", "submenu", self.map_overlay),
            ("External Data Sources", "submenu", self.external_data_sources),
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
        self.config.G_MAP = self.selected_item.title
        # reset map
        self.config.check_map_dir()
        self.config.gui.map_widget.reset_map()


class MapOverlayMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("Heatmap", "toggle", lambda: self.onoff_heatmap(True)),
            ("Heatmap List", "submenu", self.select_heatmap),
            ("Rain map", "toggle", lambda: self.onoff_rainmap(True)),
            ("Rain map List", "submenu", self.select_rainmap),
            ("Wind map", "toggle", lambda: self.onoff_windmap(True)),
            ("Wind map List", "submenu", self.select_windmap),
        )
        self.add_buttons(button_conf)

        self.onoff_heatmap(False)
        self.onoff_rainmap(False)
        self.onoff_windmap(False)

    def onoff_heatmap(self, change=True):
        self.onoff_map("Heatmap", change, self.config.G_USE_HEATMAP_OVERLAY_MAP)

    def onoff_rainmap(self, change=True):
        self.onoff_map("Rain map", change, self.config.G_USE_RAIN_OVERLAY_MAP)

    def onoff_windmap(self, change=True):
        self.onoff_map("Wind map", change, self.config.G_USE_WIND_OVERLAY_MAP)

    def onoff_map(self, overlay_type, change, is_use):
        status = is_use
        list_key = overlay_type + " List"
        if change:
            if overlay_type == "Heatmap":
                self.config.G_USE_HEATMAP_OVERLAY_MAP = not status
            elif overlay_type == "Rain map":
                self.config.G_USE_RAIN_OVERLAY_MAP = not status
            elif overlay_type == "Wind map":
                self.config.G_USE_WIND_OVERLAY_MAP = not status
            status = not status
            if self.config.display.has_touch:
                self.config.gui.map_widget.enable_overlay_button()

        self.buttons[overlay_type].change_toggle(status)

        # toggle list
        self.buttons[list_key].onoff_button(status)

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
        self.config.G_HEATMAP_OVERLAY_MAP = self.selected_item.title
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
        self.config.G_RAIN_OVERLAY_MAP = self.selected_item.title
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
        self.config.G_WIND_OVERLAY_MAP = self.selected_item.title
        # reset map
        self.config.check_map_dir()
        self.config.gui.map_widget.reset_map()


class ExternalDataSourceMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("Wind", "toggle", lambda: self.onoff_wind(True)),
            ("Wind Source", "submenu", self.select_wind_source),
            ("DEM Tile", "toggle", lambda: self.onoff_dem_tile(True)),
            ("DEM Tile source", "submenu", self.select_dem_tile),
        )
        self.add_buttons(button_conf)

        self.onoff_wind(False)
        self.onoff_dem_tile(False)

    def onoff_wind(self, change=True):
        if change:
            self.config.G_USE_WIND_DATA_SOURCE = not self.config.G_USE_WIND_DATA_SOURCE
        self.buttons["Wind"].change_toggle(self.config.G_USE_WIND_DATA_SOURCE)
        self.buttons["Wind Source"].onoff_button(self.config.G_USE_WIND_DATA_SOURCE)

    def onoff_dem_tile(self, change=True):
        if change:
            self.config.G_USE_DEM_TILE = not self.config.G_USE_DEM_TILE
        self.buttons["DEM Tile"].change_toggle(self.config.G_USE_DEM_TILE)
        self.buttons["DEM Tile source"].onoff_button(self.config.G_USE_DEM_TILE)

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
        self.config.G_WIND_DATA_SOURCE = self.selected_item.title
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
        self.config.G_DEM_MAP = self.selected_item.title
        # reset map
        self.config.check_map_dir()
