import asyncio
import os
import shutil

import numpy as np

from modules._qt_qtwidgets import (
    QT_ALIGN_CENTER,
    QtCore,
    QtGui,
    QtWidgets,
    qasync,
)
from modules.course import Course
from modules.pyqt.components import icons, topbar
from modules.pyqt.components.course_point_marker import DEFAULT_COURSE_POINT_ICON_PATH
from modules.pyqt.components.static_course_profile import StaticCourseProfileRenderer
from modules.pyqt.components.static_map import (
    GeoPoint,
    StaticMapMarker,
    StaticMapRenderer,
    StaticMapScene,
)
from modules.pyqt.pyqt_item import Item
from modules.utils.network import detect_network_async
from .pyqt_menu_widget import (
    ListItemWidget,
    ListWidget,
    MenuWidget,
)


class CoursesMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # Name(page_name), button_attribute, connected functions, icon
            ("Local Storage", "submenu", self.load_local_courses),
            (
                "Ride with GPS",
                "submenu",
                self.load_rwgps_courses,
                (
                    icons.RideWithGPSIcon(),
                    (icons.BASE_LOGO_SIZE * 4, icons.BASE_LOGO_SIZE),
                ),
            ),
            ("Android Google Maps", None, self.receive_route),
            # ('Google Routes API mode', 'submenu', self.google_routes_api_setting_menu),
            (
                "Cancel Course",
                "dialog",
                lambda: self.config.gui.show_dialog(
                    self.cancel_course, "Cancel Course"
                ),
            ),
            ("Course Traffic Side", "submenu", self.course_traffic_side),
            ("Course Calc", "toggle", lambda: self.onoff_course_calc(True)),
        )
        self.add_buttons(button_conf)

        # if not self.config.G_GOOGLE_ROUTES_API["HAVE_API_TOKEN"]:
        #  self.buttons['Google Routes API mode'].disable()

        if not self.config.G_IS_RASPI or not os.path.isfile(self.config.G_OBEXD_CMD):
            self.buttons["Android Google Maps"].disable()

        self.onoff_course_calc(False)

    def preprocess(self):
        self.onoff_course_cancel_button()

    def onoff_course_calc(self, change=True):
        if change:
            self.config.G_COURSE_INDEXING = not self.config.G_COURSE_INDEXING
        self.buttons["Course Calc"].change_toggle(self.config.G_COURSE_INDEXING)

    @qasync.asyncSlot()
    async def load_local_courses(self):
        widget = self.change_page(
            "Courses List", preprocess=True, reset=True, list_type="Local Storage"
        )
        await widget.list_local_courses()

    @qasync.asyncSlot()
    async def load_rwgps_courses(self):
        widget = self.change_page(
            "Courses List", preprocess=True, reset=True, list_type="Ride with GPS"
        )
        await widget.list_ride_with_gps(reset=True)

    def google_routes_api_setting_menu(self):
        self.change_page("Google Routes API mode", preprocess=True)

    def course_traffic_side(self):
        self.change_page("Course Traffic Side", preprocess=True)

    def onoff_course_cancel_button(self):
        status = self.config.logger.course.is_set
        self.buttons["Cancel Course"].onoff_button(status)

    def cancel_course(self, replace=False):
        self.config.logger.reset_course(delete_course_file=True, replace=replace)
        self.onoff_course_cancel_button()

    def set_new_course(self, course_file, prepared_course=None):
        self.config.logger.set_new_course(course_file, prepared_course)
        self.config.gui.init_course()
        self.onoff_course_cancel_button()

    @qasync.asyncSlot()
    async def receive_route(self):
        self.config.gui.show_dialog_cancel_only(
            self.cancel_receive_route, "Share directions > Bluetooth..."
        )
        self.is_check_folder = True
        self.status_receive = False

        self.proc_receive_route = await asyncio.create_subprocess_exec(
            self.config.G_OBEXD_CMD,
            "-d",
            "-n",
            "-r",
            os.path.abspath(self.config.G_COURSE_DIR),
            "-l",
            "-a",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        filename_search_str = "parse_name() NAME: "
        filename = None
        while True:
            if (
                self.proc_receive_route.stdout.at_eof()
                and self.proc_receive_route.stderr.at_eof()
            ):
                break

            # obexd outputs logs to stderr
            async for erdata in self.proc_receive_route.stderr:
                if erdata:
                    res_str = str(erdata.decode())
                    if res_str.find("obex_session_start()") >= 0:
                        self.status_receive = True
                    elif res_str.find(filename_search_str) >= 0:
                        num_start = res_str.find(filename_search_str) + len(
                            filename_search_str
                        )
                        filename = res_str[num_start:].strip()
                    elif res_str.find("obex_session_destroy()") >= 0:
                        self.status_receive = False
                        await self.load_file(filename)
                        break

        stdout, stderr = await self.proc_receive_route.communicate()

    @qasync.asyncSlot()
    async def cancel_receive_route(self):
        self.is_check_folder = False
        if self.proc_receive_route.returncode is None:
            self.proc_receive_route.terminate()

    async def load_file(self, filename):
        # HTML from GoogleMap App
        if filename == self.config.G_RECEIVE_COURSE_FILE:
            if not await detect_network_async():
                self.config.gui.change_dialog(
                    title="Requires network connection.", button_label="Return"
                )
            else:
                await self.load_html_route(
                    os.path.join(
                        self.config.G_COURSE_DIR, self.config.G_RECEIVE_COURSE_FILE
                    )
                )
                self.onoff_course_cancel_button()
        # course file
        elif any(extension in filename.lower() for extension in (".tcx", ".fit")):
            await self.load_course_route(filename)
        await self.cancel_receive_route()

    async def load_html_route(self, html_file):
        self.config.gui.change_dialog(title="Loading route...", button_label="Return")
        msg = ""
        try:
            self.cancel_course()
            await self.config.logger.course.load_google_map_route(
                load_html=True, html_file=html_file
            )
            msg = "Loading succeeded!"
        except asyncio.TimeoutError:
            msg = "Loading failed."
        except:
            import traceback

            traceback.print_exc()
        finally:
            self.config.gui.show_forced_message(msg)

    async def load_course_route(self, filename):
        self.cancel_course()
        extension = next(
            extension for extension in (".tcx", ".fit") if extension in filename.lower()
        )
        course_file = os.path.join(
            self.config.G_COURSE_DIR,
            filename[: filename.lower().find(extension) + len(extension)],
        )
        shutil.move(os.path.join(self.config.G_COURSE_DIR, filename), course_file)
        self.set_new_course(course_file)
        self.config.gui.show_forced_message("Loading succeeded!")


class CourseTrafficSideListWidget(ListWidget):
    settings = {
        "Left-side Traffic": "LEFT",
        "Right-side Traffic": "RIGHT",
        "None": "NONE",
    }

    def get_default_value(self):
        return next(
            label
            for label, value in self.settings.items()
            if value == self.config.G_COURSE_TRAFFIC_SIDE
        )

    async def button_func_extra(self):
        self.config.G_COURSE_TRAFFIC_SIDE = self.settings[self.selected_item.title]
        self.config.setting.write_config()
        await self.config.gui.map_widget.update_display()


class CourseListWidget(ListWidget):
    def setup_menu(self):
        super().setup_menu()
        self.vertical_scrollbar = self.list.verticalScrollBar()
        self.vertical_scrollbar.valueChanged.connect(self.detect_bottom)

    @qasync.asyncSlot(int)
    async def detect_bottom(self, value):
        if (
            self.list_type == "Ride with GPS"
            and value == self.vertical_scrollbar.maximum()
        ):
            await self.list_ride_with_gps(add=True)

    @qasync.asyncSlot()
    async def button_func(self):
        await self.change_course_detail_page()

    @qasync.asyncSlot()
    async def change_course_detail_page(self):
        if self.selected_item is None:
            return
        widget = self.change_page(
            "Course Detail",
            preprocess=True,
            course_info=self.selected_item.list_info,
            list_type=self.list_type,
        )
        await widget.load_course()

    def preprocess_extra(self):
        self.page_name_label.setText(self.list_type)

    async def list_local_courses(self):
        courses = self.config.get_courses()
        for c in courses:
            course_item = CourseListItemWidget(self, self.list_type, c)
            self.add_list_item(course_item)

    async def list_ride_with_gps(self, add=False, reset=False):
        courses = await self.config.api.get_ridewithgps_route(add, reset)

        for c in reversed(courses or []):
            course_item = CourseListItemWidget(self, self.list_type, c)
            self.add_list_item(course_item)

    def set_course(self, course_file, prepared_course):
        if self.selected_item is None:
            return

        self.course_file = course_file
        self.prepared_course = prepared_course

        # exist course: cancel and set new course
        if self.config.logger.course.is_set:
            self.config.gui.show_dialog(
                self.cancel_and_set_new_course, "Replace this course?"
            )
        else:
            self.config.gui.show_dialog(self.set_new_course, "Set this course?")

    def cancel_and_set_new_course(self):
        self.parentWidget().widget(
            self.config.gui.gui_config.G_GUI_INDEX[self.back_index_key]
        ).cancel_course(replace=True)
        self.set_new_course()

    def set_new_course(self):
        self.parentWidget().widget(
            self.config.gui.gui_config.G_GUI_INDEX[self.back_index_key]
        ).set_new_course(self.course_file, self.prepared_course)
        self.back()


class CourseListItemWidget(ListItemWidget):
    list_info = None
    list_type = None
    locality_text = ", {elevation_gain:.0f}m up, from {locality} {administrative_area}"

    def __init__(self, parent, list_type, list_info):
        self.list_type = list_type
        self.list_info = list_info.copy()

        if self.list_type == "Ride with GPS":
            detail = ("{:.1f}km" + self.locality_text).format(
                self.list_info["distance"] / 1000,
                **self.list_info,
            )
        else:
            detail = None

        super().__init__(parent=parent, title=list_info["name"], detail=detail)

        self.enter_signal.connect(parent.change_course_detail_page)

    def setup_ui(self):
        super().setup_ui()
        right_icon = icons.CourseRightIcon()
        self.outer_layout.setContentsMargins(0, 0, right_icon.margin, 0)
        self.outer_layout.addStretch()
        self.outer_layout.addWidget(right_icon)


class CourseDetailWidget(MenuWidget):
    MAP_ZOOM = 10
    MAP_MAX_POINTS = 2000
    font_size = 20

    def setup_menu(self):
        self.make_menu_layout(QtWidgets.QGridLayout)

        self.map_image = QtWidgets.QLabel()
        self.profile_image = QtWidgets.QLabel()
        for image in (self.map_image, self.profile_image):
            image.setAlignment(QT_ALIGN_CENTER)
            image.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Ignored,
                QtWidgets.QSizePolicy.Policy.Ignored,
            )

        self.map_renderer = StaticMapRenderer(
            self.config,
            zoom=self.MAP_ZOOM,
            fit_bounds=True,
        )
        self.profile_renderer = StaticCourseProfileRenderer()

        self.set_font_size()

        self.distance_item = Item(
            config=self.config,
            name="Distance",
            font_size=self.font_size,
            right_flag=self.config.gui.horizontal,
            bottom_flag=False,
        )
        self.ascent_item = Item(
            config=self.config,
            name="Ascent",
            font_size=self.font_size,
            right_flag=True,
            bottom_flag=False,
        )

        separator = QtWidgets.QWidget()
        separator.setStyleSheet("background-color: #AAAAAA")
        if self.config.gui.horizontal:
            separator.setFixedWidth(1)
            self.menu_layout.addWidget(self.map_image, 0, 0, 2, 1)
            self.menu_layout.addWidget(separator, 0, 1, 2, 1)
            self.menu_layout.addLayout(self.distance_item, 0, 2)
            self.menu_layout.addLayout(self.ascent_item, 1, 2)
            self.menu_layout.addWidget(self.profile_image, 2, 0, 1, 3)
            self.menu_layout.setColumnStretch(0, 2)
            self.menu_layout.setColumnStretch(2, 1)
            self.menu_layout.setRowStretch(0, 7)
            self.menu_layout.setRowStretch(1, 7)
            self.menu_layout.setRowStretch(2, 10)
        else:
            separator.setFixedHeight(1)
            self.menu_layout.addWidget(self.map_image, 0, 0, 1, 2)
            self.menu_layout.addWidget(separator, 1, 0, 1, 2)
            self.menu_layout.addLayout(self.distance_item, 2, 0)
            self.menu_layout.addLayout(self.ascent_item, 2, 1)
            self.menu_layout.addWidget(self.profile_image, 3, 0, 1, 2)
            self.menu_layout.setColumnStretch(0, 1)
            self.menu_layout.setColumnStretch(1, 1)
            self.menu_layout.setRowStretch(0, 8)
            self.menu_layout.setRowStretch(2, 3)
            self.menu_layout.setRowStretch(3, 4)

        # update panel for every 1 seconds
        self.timer = QtCore.QTimer(parent=self)
        self.timer.timeout.connect(self.update_display)

        # also set extra button for topbar
        self.next_button = topbar.TopBarNextButton((self.icon_x, self.icon_y))
        self.next_button.setEnabled(False)

        self.right_button_layout.addWidget(self.next_button)

        self._detail_generation = 0
        self._update_running = False
        self._reset_detail()

    def connect_buttons(self):
        self.next_button.clicked.connect(self.set_course)

    def _reset_detail(self):
        self.course_file = None
        self.route_id = None
        self.preview_course = None
        self.map_scene = None
        self.map_source_image = None
        self.profile_source_image = None
        self.map_render_key = None

    def _stop_detail_session(self):
        self._detail_generation += 1
        self.timer.stop()

    def _is_active_detail_session(self, generation, course_file):
        return generation == self._detail_generation and course_file == self.course_file

    def _get_route_json_filename(self, route_id):
        directory = self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
        return f"{directory}course-{route_id}.json"

    @staticmethod
    def _has_downloaded_file(filename):
        return os.path.exists(filename) and os.path.getsize(filename) > 0

    @staticmethod
    def _target_size(label):
        size = label.contentsRect().size()
        return size.width(), size.height()

    def _make_map_scene(self):
        course = self.preview_course
        point_count = len(course.latitude)
        step = max(1, (point_count + self.MAP_MAX_POINTS - 1) // self.MAP_MAX_POINTS)
        indices = list(range(0, point_count, step))
        if indices[-1] != point_count - 1:
            indices.append(point_count - 1)
        path = tuple(
            GeoPoint(
                latitude=float(course.latitude[index]),
                longitude=float(course.longitude[index]),
            )
            for index in indices
        )
        return StaticMapScene(
            path=path,
            markers=(
                StaticMapMarker(path[0], color="#18864B"),
                StaticMapMarker(
                    path[-1],
                    icon_path=DEFAULT_COURSE_POINT_ICON_PATH,
                ),
            ),
            line_color="#1565C0",
            line_width=4,
        )

    @staticmethod
    def _draw_image(label, image):
        target_size = CourseDetailWidget._target_size(label)
        size = QtCore.QSize(*target_size)
        if image.size() != size:
            image = image.scaled(
                size,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        label.setPixmap(QtGui.QPixmap.fromImage(image))

    def _draw_images(self):
        if self.map_source_image is not None:
            self._draw_image(self.map_image, self.map_source_image)
        if self.profile_source_image is not None:
            self._draw_image(self.profile_image, self.profile_source_image)

    def _update_course_summary(self):
        self.distance_item.update_value(
            self.course_info.get(
                "distance",
                float(self.preview_course.distance[-1]) * 1000,
            )
        )
        self.ascent_item.update_value(
            self.course_info.get("elevation_gain", self.preview_course.total_ascent)
        )

    def preprocess(self, course_info, list_type):
        self._stop_detail_session()
        self._reset_detail()

        self.map_image.clear()
        self.profile_image.clear()
        self.next_button.setVisible(False)
        self.next_button.setEnabled(False)

        self.page_name_label.setText(course_info["name"])
        self.distance_item.update_value(np.nan)
        self.ascent_item.update_value(np.nan)

        self.course_info = course_info
        if list_type == "Local Storage":
            self.course_file = course_info["path"]
        else:
            self.route_id = course_info["id"]
            self.course_file = self._get_route_json_filename(self.route_id)

        self.timer.start(self.config.G_DRAW_INTERVAL)

    async def load_course(self):
        if (
            self.route_id is not None
            and not self._has_downloaded_file(self.course_file)
            and self.config.api is not None
        ):
            await self.config.api.get_ridewithgps_files(self.route_id)
        await self._update_course_detail()

    def on_back_menu(self):
        self._stop_detail_session()

    @qasync.asyncSlot()
    async def update_display(self):
        await self._update_course_detail()

    async def _update_course_detail(self):
        if self._update_running:
            return
        self._update_running = True
        try:
            await self._render_course_detail()
        finally:
            self._update_running = False

    async def _render_course_detail(self):
        generation = self._detail_generation
        course_file = self.course_file
        if not self._is_active_detail_session(generation, course_file):
            return False

        if not self._has_downloaded_file(course_file):
            if self.route_id is None or self.config.api is None:
                self.timer.stop()
            return False

        if self.preview_course is None:
            course = Course(self.config)
            await asyncio.to_thread(course.load_preview, course_file)
            if not self._is_active_detail_session(generation, course_file):
                return False
            if not course.is_set:
                self.timer.stop()
                return False
            self.preview_course = course
            self.map_scene = self._make_map_scene()
            self.profile_source_image = self.profile_renderer.render(
                course,
                self._target_size(self.profile_image),
            )
            self._update_course_summary()
            self._draw_images()

        target_size = self._target_size(self.map_image)
        render_key = (self.config.G_MAP, target_size)
        if self.map_render_key != render_key:
            rendered = await self.map_renderer.render(self.map_scene, target_size)
            if not self._is_active_detail_session(generation, course_file):
                return False
            self.map_source_image = rendered.image
            self.map_render_key = render_key if rendered.complete else None

        self._draw_images()
        self.next_button.setVisible(True)
        self.next_button.setEnabled(True)
        complete = self.map_render_key == render_key
        if complete:
            self.timer.stop()
        return complete

    def set_course(self):
        index = self.config.gui.gui_config.G_GUI_INDEX["Courses List"]
        self.parentWidget().widget(index).set_course(
            self.course_file,
            self.preview_course,
        )

    def set_font_size(self, init=False):
        if init:
            self.font_size = int(min(self.config.display.resolution) / 10)
        else:
            self.font_size = int(min(self.size().width(), self.size().height()) / 10)

    def resizeEvent(self, event):
        if self.map_source_image is not None or self.profile_source_image is not None:
            self._draw_images()

        self.set_font_size(event.oldSize() == QtCore.QSize(-1, -1))
        for i in [self.distance_item, self.ascent_item]:
            i.update_font_size(self.font_size)

        return super().resizeEvent(event)


class GoogleRoutesAPISettingMenuWidget(ListWidget):
    def __init__(self, parent, page_name, config):
        # keys are used for item label
        self.settings = config.G_GOOGLE_ROUTES_API["API_MODE"]
        super().__init__(parent=parent, page_name=page_name, config=config)

    def get_default_value(self):
        return self.config.G_GOOGLE_ROUTES_API["API_MODE_SETTING"]

    async def button_func_extra(self):
        self.config.G_GOOGLE_ROUTES_API["API_MODE_SETTING"] = self.selected_item.title
