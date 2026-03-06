import asyncio
import os
import shutil

from PIL import Image, ImageEnhance, ImageQt

from modules._qt_qtwidgets import (
    QT_ALIGN_CENTER,
    QtCore,
    QtWidgets,
    QtGui,
    qasync,
)
from modules.pyqt.components import icons, topbar
from modules.utils.network import detect_network_async
from .pyqt_menu_widget import (
    MenuWidget,
    ListWidget,
    ListItemWidget,
)
from modules.pyqt.pyqt_item import Item


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
            ("", None, None),
            # ('Google Directions API mode', 'submenu', self.google_directions_api_setting_menu),
            (
                "Cancel Course",
                "dialog",
                lambda: self.config.gui.show_dialog(
                    self.cancel_course, "Cancel Course"
                ),
            ),
            ("Course Calc", "toggle", lambda: self.onoff_course_calc(True)),
        )
        self.add_buttons(button_conf)

        # if not self.config.G_GOOGLE_DIRECTION_API["HAVE_API_TOKEN"]:
        #  self.buttons['Google Directions API mode'].disable()

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

    def google_directions_api_setting_menu(self):
        self.change_page("Google Directions API mode", preprocess=True)

    def onoff_course_cancel_button(self):
        status = self.config.logger.course.is_set
        self.buttons["Cancel Course"].onoff_button(status)

    def cancel_course(self, replace=False):
        self.config.logger.reset_course(delete_course_file=True, replace=replace)
        self.onoff_course_cancel_button()
    
    def set_new_course(self, course_file):
        self.config.logger.set_new_course(course_file)
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
        # tcx file
        elif filename.lower().find(".tcx") >= 0:
            await self.load_tcx_route(filename)
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

    async def load_tcx_route(self, filename):
        self.cancel_course()
        course_file = os.path.join(
            self.config.G_COURSE_DIR, filename[: filename.lower().find(".tcx") + 4]
        )
        shutil.move(os.path.join(self.config.G_COURSE_DIR, filename), course_file)
        self.set_new_course(course_file)
        self.config.gui.show_forced_message("Loading succeeded!")


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
        if self.list_type == "Local Storage":
            self.set_course()
        elif self.list_type == "Ride with GPS":
            await self.change_course_detail_page()

    @qasync.asyncSlot()
    async def change_course_detail_page(self):
        if self.selected_item is None:
            return
        widget = self.change_page(
            "Course Detail",
            preprocess=True,
            course_info=self.selected_item.list_info,
        )
        await widget.load_images()

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

    def set_course(self, course_file=None):
        if self.selected_item is None:
            return

        # from Local Storage (self.list)
        if course_file is None:
            self.course_file = self.selected_item.list_info["path"]
        # from Ride with GPS (CourseDetailWidget)
        else:
            self.course_file = course_file

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
        ).set_new_course(self.course_file)
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

        if self.list_type == "Local Storage":
            self.enter_signal.connect(parent.set_course)
        elif self.list_type == "Ride with GPS":
            self.enter_signal.connect(parent.change_course_detail_page)

    def setup_ui(self):
        super().setup_ui()
        right_icon = icons.CourseRightIcon()
        self.outer_layout.setContentsMargins(0, 0, right_icon.margin, 0)
        self.outer_layout.addStretch()
        self.outer_layout.addWidget(right_icon)


class CourseDetailWidget(MenuWidget):
    list_id = None

    privacy_code = None
    all_downloaded = False
    second_download_requested = False
    map_image_size = None
    profile_image_size = None
    next_button = None
    font_size = 20

    def setup_menu(self):

        self.make_menu_layout(QtWidgets.QVBoxLayout)

        self.map_image = QtWidgets.QLabel()
        self.map_image.setAlignment(QT_ALIGN_CENTER)

        self.profile_image = QtWidgets.QLabel()
        self.profile_image.setAlignment(QT_ALIGN_CENTER)

        self.set_font_size()

        self.distance_item = Item(
            config=self.config,
            name="Distance",
            font_size=self.font_size,
            right_flag=True,
            bottom_flag=False,
        )
        self.ascent_item = Item(
            config=self.config,
            name="Ascent",
            font_size=self.font_size,
            right_flag=True,
            bottom_flag=False,
        )

        outer_layout = QtWidgets.QHBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        
        if self.config.gui.horizontal:
            info_layout = QtWidgets.QVBoxLayout()
            info_layout.setContentsMargins(0, 0, 0, 0)
            info_layout.setSpacing(0)
            info_layout.addLayout(self.distance_item)
            info_layout.addLayout(self.ascent_item)

            outer_layout.addWidget(self.map_image)
            outer_layout.addLayout(info_layout)
        else:
            self.menu_layout.addWidget(self.map_image)
            outer_layout.addLayout(self.distance_item)
            outer_layout.addLayout(self.ascent_item)

        self.menu_layout.addLayout(outer_layout)
        self.menu_layout.addWidget(self.profile_image)
        spacer = QtWidgets.QWidget()
        self.menu_layout.addWidget(spacer)

        # update panel for every 1 seconds
        self.timer = QtCore.QTimer(parent=self)
        self.timer.timeout.connect(self.update_display)

        # also set extra button for topbar
        self.next_button = topbar.TopBarNextButton((self.icon_x, self.icon_y))
        self.next_button.setEnabled(False)

        self.right_button_layout.addWidget(self.next_button)

        self._detail_active = False
        self._detail_generation = 0
        self._update_display_running = False
        self._update_display_retrigger = False
        self._reset_image_cache()

    def enable_next_button(self):
        self.next_button.setVisible(True)
        self.next_button.setEnabled(True)

    def connect_buttons(self):
        self.next_button.clicked.connect(self.set_course)

    def _reset_image_cache(self):
        self.map_image_size = None
        self.profile_image_size = None
        self.map_source_image = None
        self.profile_source_image = None
        self.map_pixmap = None
        self.profile_pixmap = None
        self._map_render_width = None
        self._profile_render_width = None

    def _start_detail_session(self):
        self._detail_generation += 1
        self._detail_active = True
        self._update_display_retrigger = False

    def _stop_detail_session(self):
        self._detail_active = False
        self._detail_generation += 1
        self._update_display_retrigger = False
        self.timer.stop()

    def _is_active_detail_session(self, generation):
        return (
            self._detail_active
            and generation == self._detail_generation
            and self.list_id is not None
        )

    def _get_map_image_filename(self, route_id):
        return (
            self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
            + "preview-{route_id}.png"
        ).format(route_id=route_id)

    def _get_profile_image_filename(self, route_id):
        return (
            self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
            + "elevation_profile-{route_id}.jpg"
        ).format(route_id=route_id)

    def _get_route_json_filename(self, route_id):
        return (
            self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
            + "course-{route_id}.json"
        ).format(route_id=route_id)

    def _get_course_filename(self, route_id):
        return (
            self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
            + "course-{route_id}.tcx"
        ).format(route_id=route_id)

    @staticmethod
    def _has_downloaded_file(filename):
        return os.path.exists(filename) and os.path.getsize(filename) > 0

    @staticmethod
    def _load_map_source_image(filename):
        with Image.open(filename) as image:
            prepared = image.convert("RGBA")
            prepared = ImageEnhance.Contrast(prepared).enhance(2.0)
            return prepared.copy()

    @staticmethod
    def _load_profile_source_image(filename):
        with Image.open(filename) as image:
            return image.convert("RGBA").copy()

    @staticmethod
    def _pil_image_to_qimage(image):
        return QtGui.QImage(ImageQt.ImageQt(image)).copy()

    async def _ensure_image_cache(
        self,
        draw_map_image=True,
        draw_profile_image=True,
        generation=None,
    ):
        if generation is None:
            generation = self._detail_generation
        if not self._is_active_detail_session(generation):
            return False

        route_id = self.list_id

        if draw_map_image and self.map_source_image is None:
            filename = self._get_map_image_filename(route_id)
            if not os.path.exists(filename):
                return False
            map_image = await asyncio.to_thread(self._load_map_source_image, filename)
            if (
                not self._is_active_detail_session(generation)
                or route_id != self.list_id
            ):
                return False
            self.map_source_image = self._pil_image_to_qimage(map_image)
            self.map_image_size = (
                self.map_source_image.width(),
                self.map_source_image.height(),
            )
            self.map_pixmap = None
            self._map_render_width = None

        if draw_profile_image and self.profile_source_image is None:
            filename = self._get_profile_image_filename(route_id)
            if not os.path.exists(filename):
                return False
            profile_image = await asyncio.to_thread(
                self._load_profile_source_image,
                filename,
            )
            if (
                not self._is_active_detail_session(generation)
                or route_id != self.list_id
            ):
                return False
            self.profile_source_image = self._pil_image_to_qimage(profile_image)
            self.profile_image_size = (
                self.profile_source_image.width(),
                self.profile_source_image.height(),
            )
            self.profile_pixmap = None
            self._profile_render_width = None

        return True

    def _draw_cached_image(
        self,
        label,
        source_image,
        target_width,
        width_attr,
        pixmap_attr,
    ):
        if (
            source_image is None
            or source_image.width() == 0
            or source_image.height() == 0
        ):
            return False

        target_width = max(1, int(target_width))
        cached_width = getattr(self, width_attr)
        pixmap = getattr(self, pixmap_attr)
        if cached_width != target_width or pixmap is None:
            scaled_image = source_image.scaledToWidth(
                target_width,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            pixmap = QtGui.QPixmap.fromImage(scaled_image)
            setattr(self, width_attr, target_width)
            setattr(self, pixmap_attr, pixmap)

        label.setPixmap(pixmap)
        return True

    def preprocess(self, course_info):
        self._stop_detail_session()

        # reset
        self.list_id = None
        self.privacy_code = None
        self.all_downloaded = False
        self.second_download_requested = False
        self._reset_image_cache()

        self.map_image.clear()
        self.profile_image.clear()
        self.next_button.setVisible(False)
        self.next_button.setEnabled(False)

        self.page_name_label.setText(course_info["name"])
        self.distance_item.update_value(course_info["distance"])
        self.ascent_item.update_value(course_info["elevation_gain"])

        self.list_id = course_info["id"]

        self._start_detail_session()
        self.timer.start(self.config.G_DRAW_INTERVAL)

    async def load_images(self):
        generation = self._detail_generation
        if not self._is_active_detail_session(generation):
            return
        if await self.check_all_image_and_draw(generation):
            if self._is_active_detail_session(generation):
                self.timer.stop()
            return
        if self.config.api is None:
            return

        # 1st download
        await self.config.api.get_ridewithgps_files(self.list_id)

    def on_back_menu(self):
        self._stop_detail_session()

    @qasync.asyncSlot()
    async def update_display(self):
        if self._update_display_running:
            self._update_display_retrigger = True
            return

        self._update_display_running = True
        try:
            generation = self._detail_generation
            if not self._is_active_detail_session(generation):
                return

            if await self.check_all_image_and_draw(generation):
                if self._is_active_detail_session(generation):
                    self.timer.stop()
                return

            if self.config.api is None:
                return

            route_id = self.list_id
            has_route_json = self._has_downloaded_file(
                self._get_route_json_filename(route_id)
            )
            has_map_preview = self._has_downloaded_file(
                self._get_map_image_filename(route_id)
            )

            # Start the 2nd download as soon as the route JSON is available.
            if has_route_json and not self.second_download_requested:
                if has_map_preview:
                    if not await self._ensure_image_cache(
                        draw_map_image=True,
                        draw_profile_image=False,
                        generation=generation,
                    ):
                        return
                    if not self._is_active_detail_session(generation):
                        return
                    self.draw_images(draw_map_image=True, draw_profile_image=False)

                self.privacy_code = (
                    self.config.logger.course.get_ridewithgps_privacycode(route_id)
                )
                self.second_download_requested = True
                await self.config.api.get_ridewithgps_files_with_privacy_code(
                    route_id, self.privacy_code
                )
        finally:
            self._update_display_running = False
            if self._detail_active and self._update_display_retrigger:
                self._update_display_retrigger = False
                QtCore.QTimer.singleShot(0, self.update_display)

    async def check_all_image_and_draw(self, generation):
        if self.list_id is None:
            return False

        has_map_preview = self._has_downloaded_file(
            self._get_map_image_filename(self.list_id)
        )
        has_profile = self._has_downloaded_file(
            self._get_profile_image_filename(self.list_id)
        )
        has_course_file = self._has_downloaded_file(
            self._get_course_filename(self.list_id)
        )

        if has_map_preview or has_profile:
            if not await self._ensure_image_cache(
                draw_map_image=has_map_preview,
                draw_profile_image=has_profile,
                generation=generation,
            ):
                return False
            if not self._is_active_detail_session(generation):
                return False
            self.draw_images(
                draw_map_image=has_map_preview,
                draw_profile_image=has_profile,
            )

        if has_course_file:
            self.all_downloaded = True
            self.enable_next_button()
            return True

        return False

    def set_course(self):
        index = self.config.gui.gui_config.G_GUI_INDEX["Courses List"]
        self.parentWidget().widget(index).set_course(
            (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
                + "course-{route_id}.tcx"
            ).format(route_id=self.list_id)
        )

    def draw_images(self, draw_map_image=True, draw_profile_image=True):

        if self.list_id is None:
            return False

        if draw_map_image:
            if self.map_image_size is None:
                return False

            ratio = 1
            if self.config.gui.horizontal:
                ratio = 0.5
            if not self._draw_cached_image(
                self.map_image,
                self.map_source_image,
                self.size().width() * ratio,
                "_map_render_width",
                "map_pixmap",
            ):
                return False

        if draw_profile_image:
            if self.profile_image_size is None:
                return False

            if not self._draw_cached_image(
                self.profile_image,
                self.profile_source_image,
                self.size().width(),
                "_profile_render_width",
                "profile_pixmap",
            ):
                return False

        return True

    def set_font_size(self, init=False):
        if init:
            self.font_size = int(min(self.config.display.resolution) / 10)
        else:
            self.font_size = int(min(self.size().width(), self.size().height()) / 10)

    def resizeEvent(self, event):
        if self.map_source_image is not None or self.profile_source_image is not None:
            self.draw_images(
                draw_map_image=self.map_source_image is not None,
                draw_profile_image=self.profile_source_image is not None,
            )

        self.set_font_size(event.oldSize() == QtCore.QSize(-1, -1))
        for i in [self.distance_item, self.ascent_item]:
            i.update_font_size(self.font_size)

        return super().resizeEvent(event)


class GoogleDirectionsAPISettingMenuWidget(ListWidget):
    def __init__(self, parent, page_name, config):
        # keys are used for item label
        self.settings = config.G_GOOGLE_DIRECTION_API["API_MODE"]
        super().__init__(parent=parent, page_name=page_name, config=config)

    def get_default_value(self):
        return self.config.G_GOOGLE_DIRECTION_API["API_MODE_SETTING"]

    async def button_func_extra(self):
        self.config.G_GOOGLE_DIRECTION_API[
            "API_MODE_SETTING"
        ] = self.selected_item.title
