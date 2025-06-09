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
from modules.utils.network import detect_network
from .pyqt_menu_widget import (
    MenuWidget,
    ListWidget,
    ListItemWidget,
)
from modules.pyqt.pyqt_item import Item


class CoursesMenuWidget(MenuWidget):
    def setup_menu(self):
        button_conf = (
            # MenuConfig Key, Name(page_name), button_attribute, connected functions, icon
            ("LOCAL_STORAGE", "Local Storage", "submenu", self.load_local_courses),
            (   "RIDE_WITH_GPS",
                "Ride with GPS",
                "submenu",
                self.load_rwgps_courses,
                (
                    icons.RideWithGPSIcon(),
                    (icons.BASE_LOGO_SIZE * 4, icons.BASE_LOGO_SIZE),
                ),
            ),
            ("ANDROID_GOOGLE_MAPS", "Android Google Maps", None, self.receive_route),
            ("COURSE_EMPTY", "", None, None),
            # ('Google Directions API mode', 'submenu', self.google_directions_api_setting_menu),
            (   "COURSE_CANCEL",
                "Cancel Course",
                "dialog",
                lambda: self.config.gui.show_dialog(
                    self.cancel_course, "Cancel Course"
                ),
            ),
            ("COURSE_CALCULATION", "Course Calc", "toggle", lambda: self.onoff_course_calc(True)),
        )
        self.add_buttons(button_conf)

        # if not self.config.G_GOOGLE_DIRECTION_API["HAVE_API_TOKEN"]:
        #  self.buttons.disable_if_exists('Google Directions API mode')

        if not self.config.G_IS_RASPI or not os.path.isfile(self.config.G_OBEXD_CMD):
            self.buttons.disable_if_exists("ANDROID_GOOGLE_MAPS")

        self.onoff_course_calc(False)

    def preprocess(self):
        self.onoff_course_cancel_button()

    def onoff_course_calc(self, change=True):
        if change:
            self.config.G_COURSE_INDEXING = not self.config.G_COURSE_INDEXING
        self.buttons.change_toggle_if_exists("COURSE_CALCULATION", self.config.G_COURSE_INDEXING)

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
        self.buttons.onoff_button_if_exists("COURSE_CANCEL", status)

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
            if not detect_network():
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
    map_image_size = None
    profile_image_size = None
    next_button = None
    horizontal = True
    font_size = 20

    def setup_menu(self):
        if self.parent().size().height() > self.parent().size().width():
            self.horizontal = False

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
        
        if self.horizontal:
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

        self.top_bar_layout.addWidget(self.next_button)

    def enable_next_button(self):
        self.next_button.setVisible(True)
        self.next_button.setEnabled(True)

    def connect_buttons(self):
        self.next_button.clicked.connect(self.set_course)

    def preprocess(self, course_info):
        # reset
        self.list_id = None
        self.privacy_code = None
        self.all_downloaded = False

        self.map_image.clear()
        self.profile_image.clear()
        self.next_button.setVisible(False)
        self.next_button.setEnabled(False)

        self.page_name_label.setText(course_info["name"])
        self.distance_item.update_value(course_info["distance"])
        self.ascent_item.update_value(course_info["elevation_gain"])

        self.list_id = course_info["id"]

        self.timer.start(self.config.G_DRAW_INTERVAL)

    async def load_images(self):
        if self.check_all_image_and_draw():
            self.timer.stop()
            return
        else:
            # 1st download
            await self.config.api.get_ridewithgps_files(self.list_id)

    def on_back_menu(self):
        self.timer.stop()

    @qasync.asyncSlot()
    async def update_display(self):
        if self.check_all_image_and_draw():
            self.timer.stop()
            return

        # sequentially draw with download
        # 1st download check
        if self.privacy_code is None and self.config.api.check_ridewithgps_files(
            self.list_id, "1st"
        ):
            self.draw_images(draw_map_image=True, draw_profile_image=False)
            self.privacy_code = self.config.logger.course.get_ridewithgps_privacycode(
                self.list_id
            )
            if self.privacy_code is not None:
                # download files with privacy code (2nd download)
                await self.config.api.get_ridewithgps_files_with_privacy_code(
                    self.list_id, self.privacy_code
                )
        # 2nd download with privacy_code check
        elif self.privacy_code is not None and self.config.api.check_ridewithgps_files(
            self.list_id, "2nd"
        ):
            self.draw_images(draw_map_image=False, draw_profile_image=True)
            self.enable_next_button()
            self.timer.stop()

    def check_all_image_and_draw(self):
        # if all files exists, reload images and buttons, stop timer and exit
        if not self.all_downloaded and self.config.api is not None:
            self.all_downloaded = self.config.api.check_ridewithgps_files(
                self.list_id, "ALL"
            )
        if self.all_downloaded:
            res = self.draw_images()
            self.enable_next_button()
            return res
        # if no internet connection, stop timer and exit
        elif not detect_network():
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
            filename = (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
                + "preview-{route_id}.png"
            ).format(route_id=self.list_id)
            if not os.path.exists(filename):
                return

            im = Image.open(filename).convert("RGBA")
            im = ImageEnhance.Contrast(im).enhance(2.0)
            if self.map_image_size is None:
                self.map_image_size = Image.open(filename).size # tuple (w, h)
            if self.map_image_size[0] == 0 or self.map_image_size[1] == 0:
                return False

            ratio = 1 # ratio against window width (for vertical layout)
            if self.horizontal:
                ratio = 0.5
            scale = (self.size().width() * ratio) / self.map_image_size[0]
            im = im.resize((
                int(self.map_image_size[0] * scale),
                int(self.map_image_size[1] * scale),
            ))
            self.map_image.setPixmap(QtGui.QPixmap.fromImage(ImageQt.ImageQt(im)))

        if draw_profile_image:
            filename = (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
                + "elevation_profile-{route_id}.jpg"
            ).format(route_id=self.list_id)

            im = Image.open(filename).convert("RGBA")
            if self.profile_image_size is None:
                self.profile_image_size = Image.open(filename).size # tuple (w, h)
            if self.profile_image_size[0] == 0 or self.profile_image_size[1] == 0:
                return False

            scale = self.size().width() / self.profile_image_size[0]
            im = im.resize((
                int(self.profile_image_size[0] * scale),
                int(self.profile_image_size[1] * scale),
            ))
            self.profile_image.setPixmap(QtGui.QPixmap.fromImage(ImageQt.ImageQt(im)))

        return True

    def set_font_size(self, init=False):
        if init:
            self.font_size = int(min(self.config.display.resolution) / 10)
        else:
            self.font_size = int(min(self.size().width(), self.size().height()) / 10)

    def resizeEvent(self, event):
        self.check_all_image_and_draw()

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
        ] = self.selected_item.title_label.text()
