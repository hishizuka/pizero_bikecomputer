try:
    import PyQt6.QtCore as QtCore
    import PyQt6.QtWidgets as QtWidgets
    import PyQt6.QtGui as QtGui
except ImportError:
    import PyQt5.QtCore as QtCore
    import PyQt5.QtWidgets as QtWidgets
    import PyQt5.QtGui as QtGui

import asyncio
import os
import shutil
from qasync import asyncSlot

from .pyqt_menu_widget import MenuWidget, ListWidget, ListItemWidget


class CoursesMenuWidget(MenuWidget):
    def setup_menu(self):
        self.button = {}
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("Local Storage", "submenu", self.load_local_courses),
            (
                "Ride with GPS",
                "submenu",
                self.load_rwgps_courses,
                "./img/rwgps_logo.svg",
                QtCore.QSize(self.logo_size * 4, self.logo_size),
            ),
            ("Android Google Maps", None, self.receive_route),
            # ('Google Directions API mode', 'submenu', self.google_directions_api_setting_menu),
            (
                "Cancel Course",
                "dialog",
                lambda: self.config.gui.show_dialog(
                    self.cancel_course, "Cancel Course"
                ),
            ),
        )
        self.add_buttons(button_conf, back_connect=False)

        # if not self.config.G_GOOGLE_DIRECTION_API["HAVE_API_TOKEN"]:
        #  self.button['Google Directions API mode'].disable()

        if not self.config.G_IS_RASPI or not os.path.isfile(self.config.G_OBEXD_CMD):
            self.button["Android Google Maps"].disable()

        # set back_index of child widget
        self.child_page_name = "Courses List"
        self.child_index = self.config.gui.gui_config.G_GUI_INDEX[self.child_page_name]
        self.parentWidget().widget(self.child_index).back_index_key = self.page_name

        # index = self.config.gui.gui_config.G_GUI_INDEX['Google Directions API mode']
        # self.parentWidget().widget(index).back_index_key = self.page_name

    def preprocess(self):
        self.onoff_course_cancel_button()

    @asyncSlot()
    async def load_local_courses(self):
        await self.change_course_page("Local Storage")
        await self.parentWidget().widget(self.child_index).list_local_courses()

    @asyncSlot()
    async def load_rwgps_courses(self):
        asyncio.gather(
            self.change_course_page("Ride with GPS"),
            self.parentWidget().widget(self.child_index).list_ride_with_gps(reset=True),
        )

    async def change_course_page(self, course_type):
        self.change_page(
            self.child_page_name, preprocess=True, reset=True, list_type=course_type
        )

    def google_directions_api_setting_menu(self):
        self.change_page("Google Directions API mode", preprocess=True)

    def onoff_course_cancel_button(self):
        if not len(self.config.logger.course.distance):
            self.button["Cancel Course"].disable()
        else:
            self.button["Cancel Course"].enable()
        self.button["Cancel Course"].setStyleSheet(
            self.config.gui.style.G_GUI_PYQT_buttonStyle_menu
        )

    def cancel_course(self, replace=False):
        self.config.logger.reset_course(delete_course_file=True, replace=replace)
        self.onoff_course_cancel_button()

    @asyncSlot()
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
            self.config.G_COURSE_DIR,
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

    @asyncSlot()
    async def cancel_receive_route(self):
        self.is_check_folder = False
        if self.proc_receive_route.returncode is None:
            self.proc_receive_route.terminate()

    async def load_file(self, filename):
        # HTML from GoogleMap App
        if filename == self.config.G_RECEIVE_COURSE_FILE:
            await self.load_html_route(
                self.config.G_COURSE_DIR + self.config.G_RECEIVE_COURSE_FILE
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
        course_file = (
            self.config.G_COURSE_DIR + filename[: filename.lower().find(".tcx") + 4]
        )
        shutil.move(self.config.G_COURSE_DIR + filename, course_file)
        self.set_new_course(course_file)
        self.config.gui.show_forced_message("Loading succeeded!")

    def set_new_course(self, course_file):
        self.config.logger.set_new_course(course_file)
        self.config.gui.init_course()
        self.onoff_course_cancel_button()


class CourseListWidget(ListWidget):
    def setup_menu_extra(self):
        # set back_index of child widget
        self.child_page_name = "Course Detail"
        self.child_index = self.config.gui.gui_config.G_GUI_INDEX[self.child_page_name]
        self.parentWidget().widget(self.child_index).back_index_key = self.page_name

        self.vertical_scrollbar = self.list.verticalScrollBar()
        self.vertical_scrollbar.valueChanged.connect(self.detect_bottom)

    @asyncSlot(int)
    async def detect_bottom(self, value):
        if self.list_type == "Ride with GPS":
            if value == self.vertical_scrollbar.maximum():
                await self.list_ride_with_gps(add=True)

    @asyncSlot()
    async def button_func(self):
        if self.list_type == "Local Storage":
            self.set_course()
        elif self.list_type == "Ride with GPS":
            await self.change_course_detail_page()

    @asyncSlot()
    async def change_course_detail_page(self):
        if self.selected_item is None:
            return
        self.change_page(
            self.child_page_name,
            preprocess=True,
            course_info=self.selected_item.list_info,
        )
        await self.parentWidget().widget(self.child_index).load_images()

    def preprocess_extra(self):
        self.page_name_label.setText(self.list_type)

    async def list_local_courses(self):
        courses = self.config.logger.course.get_courses()
        for c in courses:
            course_item = CourseListItemWidget(self, self.config, self.list_type)
            course_item.set_info(**c)
            self.add_list_item(course_item)

    async def list_ride_with_gps(self, add=False, reset=False):
        courses = await self.config.network.api.get_ridewithgps_route(add, reset)
        if courses is None:
            return

        for c in reversed(courses):
            course_item = CourseListItemWidget(self, self.config, self.list_type)
            course_item.set_info(**c)
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
        if len(self.config.logger.course.distance):
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
    list_type = None
    locality_text = ""

    def __init__(self, parent, config, list_type=None):
        super().__init__(parent=parent, config=config)
        self.list_type = list_type

        if self.list_type == "Local Storage":
            self.enter_signal.connect(self.parentWidget().set_course)
            self.set_simple_list_stylesheet(hide_detail_label=True)
        elif self.list_type == "Ride with GPS":
            self.enter_signal.connect(self.parentWidget().change_course_detail_page)
            self.set_simple_list_stylesheet()
            self.locality_text = (
                ", {elevation_gain:.0f}m up, {locality}, {administrative_area}"
            )
            if self.config.G_LANG in [
                "JA",
            ]:
                self.locality_text = (
                    ", {elevation_gain:.0f}m up, {administrative_area}{locality}"
                )

    def add_extra(self):
        self.right_icon = QtWidgets.QLabel()
        icon_size = self.parentWidget().MenuButton.icon_size["submenu"]
        right_icon_qsize = QtCore.QSize(icon_size, icon_size)
        self.right_icon.setPixmap(
            self.parentWidget().MenuButton.icon_img["submenu"].pixmap(right_icon_qsize)
        )
        self.right_icon.setStyleSheet(self.config.gui.style.G_GUI_PYQT_menu_list_border)

        # outer layout (custom)
        self.outer_layout.setContentsMargins(
            0, 0, self.parentWidget().MenuButton.icon_margin["submenu"] + 1, 0
        )
        self.outer_layout.addLayout(
            self.inner_layout, self.config.gui.gui_config.align_left
        )
        self.outer_layout.addStretch()
        self.outer_layout.addWidget(self.right_icon)

    def set_info(self, **kargs):
        self.list_info = kargs.copy()
        self.title_label.setText(self.list_info["name"])
        if self.list_type == "Ride with GPS":
            self.detail_label.setText(
                ("{:.1f}km" + self.locality_text).format(
                    self.list_info["distance"] / 1000,
                    **self.list_info,
                )
            )


class CourseDetailWidget(MenuWidget):
    list_id = None

    privacy_code = None
    all_downloaded = False
    map_image_size = None
    profile_image_size = None

    def setup_menu(self):
        self.make_menu_layout(QtWidgets.QVBoxLayout)

        self.map_image = QtWidgets.QLabel()
        self.map_image.setAlignment(self.config.gui.gui_config.align_center)

        self.profile_image = QtWidgets.QLabel()
        self.profile_image.setAlignment(self.config.gui.gui_config.align_center)

        self.distance_label = QtWidgets.QLabel()
        self.distance_label.setMargin(0)
        self.distance_label.setContentsMargins(0, 0, 0, 0)

        self.elevation_label = QtWidgets.QLabel()
        self.elevation_label.setMargin(0)
        self.elevation_label.setContentsMargins(0, 0, 0, 0)

        self.locality_label = QtWidgets.QLabel()
        self.locality_label.setMargin(0)
        self.locality_label.setContentsMargins(0, 0, 0, 0)
        self.locality_label.setWordWrap(True)

        self.info_layout = QtWidgets.QVBoxLayout()
        self.info_layout.setContentsMargins(5, 0, 0, 0)
        self.info_layout.setSpacing(0)
        self.info_layout.addWidget(self.distance_label)
        self.info_layout.addWidget(self.elevation_label)
        self.info_layout.addWidget(self.locality_label)

        self.outer_layout = QtWidgets.QHBoxLayout()
        self.outer_layout.setContentsMargins(0, 0, 0, 0)
        self.outer_layout.setSpacing(0)
        self.outer_layout.addWidget(self.map_image)
        self.outer_layout.addLayout(self.info_layout)

        self.menu_layout.addLayout(self.outer_layout)
        self.menu_layout.addWidget(self.profile_image)

        self.address_format = "{locality}, {administrative_area}"
        if self.config.G_LANG in [
            "JA",
        ]:
            self.address_format = "{administrative_area}{locality}"

        # update panel for every 1 seconds
        self.timer = QtCore.QTimer(parent=self)
        self.timer.timeout.connect(self.update_display)

    def enable_next_button(self):
        self.next_button.setEnabled(True)
        self.next_button.setIcon(
            QtGui.QIcon(self.config.gui.gui_config.icon_dir + "img/forward_white.svg")
        )
        self.next_button.setIconSize(QtCore.QSize(20, 20))
        self.next_button.setProperty("style", "menu")
        self.next_button.setStyleSheet(
            self.config.gui.style.G_GUI_PYQT_buttonStyle_navi
        )

    def connect_buttons(self):
        self.next_button.clicked.connect(self.set_course)

    def preprocess(self, course_info):
        # reset
        self.list_id = None
        self.privacy_code = None
        self.all_downloaded = False

        self.map_image.clear()
        self.profile_image.clear()
        self.next_button.setIcon(QtGui.QIcon())
        self.next_button.setEnabled(False)

        self.page_name_label.setText(course_info["name"])
        self.distance_label.setText("{:.1f}km".format(course_info["distance"] / 1000))
        self.elevation_label.setText("{:.0f}m up".format(course_info["elevation_gain"]))
        self.locality_label.setText(self.address_format.format(**course_info))

        self.list_id = course_info["name"]

        self.timer.start(self.config.G_DRAW_INTERVAL)

    async def load_images(self):
        if self.check_all_image_and_draw():
            self.timer.stop()
            return
        else:
            # 1st download
            await self.config.network.api.get_ridewithgps_files(self.list_id)

    def on_back_menu(self):
        self.timer.stop()

    @asyncSlot()
    async def update_display(self):
        if self.check_all_image_and_draw():
            self.timer.stop()
            return

        # sequentially draw with download
        # 1st download check
        if (
            self.privacy_code is None
            and self.config.network.api.check_ridewithgps_files(self.list_id, "1st")
        ):
            self.draw_images(draw_map_image=True, draw_profile_image=False)
            self.privacy_code = self.config.logger.course.get_ridewithgps_privacycode(
                self.list_id
            )
            if self.privacy_code is not None:
                # download files with privacy code (2nd download)
                await self.config.network.api.get_ridewithgps_files_with_privacy_code(
                    self.list_id, self.privacy_code
                )
        # 2nd download with privacy_code check
        elif (
            self.privacy_code is not None
            and self.config.network.api.check_ridewithgps_files(self.list_id, "2nd")
        ):
            self.draw_images(draw_map_image=False, draw_profile_image=True)
            self.enable_next_button()
            self.timer.stop()

    def check_all_image_and_draw(self):
        # if all files exists, reload images and buttons, stop timer and exit
        if not self.all_downloaded and self.config.network is not None:
            self.all_downloaded = self.config.network.api.check_ridewithgps_files(
                self.list_id, "ALL"
            )
        if self.all_downloaded:
            res = self.draw_images()
            self.enable_next_button()
            return res
        # if no internet connection, stop timer and exit
        elif not self.config.detect_network():
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
            if self.map_image_size is None:
                # self.map_image_size = Image.open(filename).size
                self.map_image_size = QtGui.QImage(filename).size()
            if self.map_image_size.width() == 0:
                return False
            scale = (self.menu.width() / 2) / self.map_image_size.width()
            self.map_image_qsize = QtCore.QSize(
                int(self.map_image_size.width() * scale),
                int(self.map_image_size.height() * scale),
            )
            self.map_image.setPixmap(QtGui.QIcon(filename).pixmap(self.map_image_qsize))

        if draw_profile_image:
            filename = (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
                + "elevation_profile-{route_id}.jpg"
            ).format(route_id=self.list_id)
            if self.profile_image_size is None:
                # self.profile_image_size = Image.open(filename).size
                self.profile_image_size = QtGui.QImage(filename).size()
            if self.profile_image_size.width() == 0:
                return False
            scale = self.menu.width() / self.profile_image_size.width()
            self.profile_image_qsize = QtCore.QSize(
                int(self.profile_image_size.width() * scale),
                int(self.profile_image_size.height() * scale),
            )
            self.profile_image.setPixmap(
                QtGui.QIcon(filename).pixmap(self.profile_image_qsize)
            )
        return True

    def resizeEvent(self, event):
        self.check_all_image_and_draw()

        h = self.size().height()
        q = self.distance_label.font()
        q.setPixelSize(int(h / 12))
        for l in [self.distance_label, self.elevation_label, self.locality_label]:
            l.setFont(q)

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
