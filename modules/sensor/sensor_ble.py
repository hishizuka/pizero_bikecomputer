import asyncio
import math
import os
import re
import signal
import sys
from typing import Optional

from modules.app_logger import app_logger
from modules.utils.cmd import start_process

from .ble.adapter import (
    BleAdapterPolicy,
    BleAdapterResolutionError,
    BleAdapterResolver,
)
from .ble.health import BleSessionHealth
from .sensor import Sensor

_HAS_BLE_CYCLING = False
try:
    import bleak
    import pycycling  # noqa: F401

    from .ble.cps import CpsPowerProcessor
    from .ble.csc import CscCadenceProcessor, CscSpeedProcessor
    from .ble.cycling import (
        BleCyclingCandidate,
        BleCyclingSession,
        PROFILE_CPS,
        PROFILE_CSCS,
        PROFILE_HRS,
        discover_cycling_devices,
    )
    from .ble.hrs import HrsHeartRateProcessor

    _HAS_BLE_CYCLING = True
except ImportError:
    pass

_HAS_ZWIFT_CLICK_V2 = False
try:
    from .ble import zwift_click_v2
    import bleak

    _HAS_ZWIFT_CLICK_V2 = True
except ImportError:
    pass

if _HAS_ZWIFT_CLICK_V2 or _HAS_BLE_CYCLING:
    app_logger.info("  BLE")


class SensorBLE(Sensor):
    CYCLING_ROLES = ("HR", "SPD", "CDC", "PWR")
    _zwift_click_v2_stop_event: Optional[asyncio.Event] = None
    _zwift_click_v2_task: Optional[asyncio.Task] = None

    def __init__(self, config, values):
        super().__init__(config, values)
        self._fake_trainer_proc = None
        self._fake_trainer_check_handle = None
        self._cycling_paused_for_fake_trainer = False
        self._zwift_click_v2_paused_for_fake_trainer = False
        self._fake_trainer_session_active = False
        self._cycling_health = {role: BleSessionHealth() for role in self.CYCLING_ROLES}
        self._zwift_click_v2_health = BleSessionHealth()
        self._cycling_discovered_devices = {}
        self._cycling_discovered_profiles = {}
        self._hrs_heart_rate_processor = None
        self._csc_speed_processor = None
        self._csc_cadence_processor = None
        self._cps_power_processor = None
        if _HAS_BLE_CYCLING:
            self._hrs_heart_rate_processor = HrsHeartRateProcessor(
                health=self._cycling_health["HR"],
            )
            self._csc_speed_processor = CscSpeedProcessor(
                self.config.G_WHEEL_CIRCUMFERENCE,
                health=self._cycling_health["SPD"],
            )
            self._csc_cadence_processor = CscCadenceProcessor(
                health=self._cycling_health["CDC"],
            )
            self._cps_power_processor = CpsPowerProcessor(
                health=self._cycling_health["PWR"],
            )
        self._cycling_processors = {
            "HR": self._hrs_heart_rate_processor,
            "SPD": self._csc_speed_processor,
            "CDC": self._csc_cadence_processor,
            "PWR": self._cps_power_processor,
        }
        self._publish_cycling_values()

    def sensor_init(self):
        self._cycling_stop_events = {}
        self._cycling_tasks = {}
        self._cycling_session_roles = {}
        self._zwift_click_v2_stop_event = asyncio.Event()
        self._zwift_click_v2_task = None

    def reset(self):
        if self._csc_speed_processor is not None:
            self._csc_speed_processor.reset_distance()
        if self._cps_power_processor is not None:
            self._cps_power_processor.reset_accumulated_power()
        self._publish_cycling_values()

    def _reset_zwift_click_v2_runtime(self) -> None:
        self._zwift_click_v2_stop_event = asyncio.Event()
        self._zwift_click_v2_task = None

    def start_coroutine(self):
        self.connect_cycling_sensors()
        self.connect_zwift_click_v2()

    def quit(self):
        self._fake_trainer_session_active = False
        self._cycling_paused_for_fake_trainer = False
        self._zwift_click_v2_paused_for_fake_trainer = False
        self.stop_fake_trainer()
        self.disconnect_cycling_sensors()
        self.disconnect_zwift_click_v2()
        for role, health_record in self._cycling_health.items():
            health = health_record.snapshot().as_dict()
            app_logger.debug(f"[BLE_HEALTH] cycling_{role.lower()}={health}")
        health = self._zwift_click_v2_health.snapshot().as_dict()
        app_logger.debug(f"[BLE_HEALTH] zwift_click_v2={health}")

    def update(self) -> None:
        for processor in self._cycling_processors.values():
            if processor is None:
                continue
            processor.tick()
            processor.report_notification_silence()
        self._publish_cycling_values()

    def _publish_cycling_values(self) -> None:
        self._publish_hrs_heart_rate_values()
        self._publish_csc_speed_values()
        self._publish_csc_cadence_values()
        self._publish_cps_power_values()

    def _publish_hrs_heart_rate_values(self) -> None:
        processor = self._hrs_heart_rate_processor
        if processor is None:
            self.values["HR"] = {
                "heart_rate": math.nan,
                "sensor_contact": None,
                "energy_expended": None,
                "rr_intervals": (),
                "status": "inactive",
                "measured_at": None,
                "received_at": None,
            }
            return
        reading = processor.heart_rate
        self.values["HR"] = {
            "heart_rate": reading.value,
            "sensor_contact": processor.sensor_contact,
            "energy_expended": processor.energy_expended,
            "rr_intervals": processor.rr_intervals,
            "status": processor.status.value,
            "measured_at": reading.measured_at,
            "received_at": reading.received_at,
        }

    def _publish_csc_speed_values(self) -> None:
        processor = self._csc_speed_processor
        if processor is None:
            self.values["SPD"] = {
                "speed": math.nan,
                "distance": 0.0,
                "status": "inactive",
                "measured_at": None,
                "received_at": None,
            }
            return
        reading = processor.speed
        self.values["SPD"] = {
            "speed": reading.value,
            "distance": processor.distance,
            "status": processor.status.value,
            "measured_at": reading.measured_at,
            "received_at": reading.received_at,
        }

    def _publish_csc_cadence_values(self) -> None:
        processor = self._csc_cadence_processor
        if processor is None:
            self.values["CDC"] = {
                "cadence": math.nan,
                "status": "inactive",
                "measured_at": None,
                "received_at": None,
            }
            return
        reading = processor.cadence
        self.values["CDC"] = {
            "cadence": reading.value,
            "status": processor.status.value,
            "measured_at": reading.measured_at,
            "received_at": reading.received_at,
        }

    def _publish_cps_power_values(self) -> None:
        processor = self._cps_power_processor
        if processor is None:
            self.values["PWR"] = {
                "power": math.nan,
                "accumulated_power": 0.0,
                "status": "inactive",
                "measured_at": None,
                "received_at": None,
            }
            return
        reading = processor.power
        self.values["PWR"] = {
            "power": reading.value,
            "accumulated_power": processor.accumulated_power,
            "status": processor.status.value,
            "measured_at": reading.measured_at,
            "received_at": reading.received_at,
        }

    def is_sensor_available(self, role: str) -> bool:
        if role not in self.CYCLING_ROLES or not _HAS_BLE_CYCLING:
            return False
        return bool(
            self.config.ble_sensor_enabled()
            and self.config.is_sensor_configured(role, self.config.SENSOR_PROTOCOL_BLE)
        )

    def is_sensor_connected(self, role: str) -> bool:
        if role not in self.CYCLING_ROLES:
            return False
        processor = self._cycling_processors[role]
        if processor is None:
            return False
        return processor.status.value == "connected"

    def get_sensor_connection_status(self, role: str) -> str:
        if not self.config.sensor_uses(role, self.config.SENSOR_PROTOCOL_BLE):
            return "inactive"
        if not self.is_sensor_available(role):
            return "disconnected"
        status = self._cycling_processors[role].status.value
        if status in ("connected", "disconnected"):
            return status
        return "connecting"

    def can_scan_cycling_sensors(self, role: str | None = None) -> bool:
        return bool(
            (role is None or role in self.CYCLING_ROLES)
            and _HAS_BLE_CYCLING
            and self.config.ble_sensor_enabled()
            and not self.is_fake_trainer_running()
        )

    def _scan_profiles_for_role(self, role: str) -> tuple[str, ...]:
        if role == "HR":
            return (PROFILE_HRS,)
        if role == "SPD":
            return (PROFILE_CSCS,)
        if role == "PWR":
            return (PROFILE_CPS,)
        if role == "CDC":
            return (PROFILE_CSCS, PROFILE_CPS)
        return ()

    async def discover_cycling_sensors(
        self,
        role: str,
        timeout: float = 10.0,
    ) -> list["BleCyclingCandidate"]:
        self._cycling_discovered_devices.clear()
        self._cycling_discovered_profiles.clear()
        if not self.can_scan_cycling_sensors(role):
            return []
        adapter = self._resolve_sensor_adapter()
        if sys.platform.startswith("linux") and adapter is None:
            return []
        devices = await discover_cycling_devices(
            timeout=timeout,
            adapter=adapter,
            profiles=self._scan_profiles_for_role(role),
        )
        self._cycling_discovered_devices = {
            candidate.identifier: device for device, candidate in devices
        }
        self._cycling_discovered_profiles = {
            candidate.identifier: candidate.profiles for _device, candidate in devices
        }
        return [candidate for _device, candidate in devices]

    def set_cycling_sensor(
        self,
        role: str,
        identifier: str,
        name: str = "",
        profile: str | None = None,
    ) -> None:
        if role not in self.CYCLING_ROLES:
            raise ValueError(f"Unsupported BLE cycling role: {role}")
        identifier = identifier.strip()
        if not identifier:
            raise ValueError("identifier must not be empty")
        profile = self._select_pairing_profile(role, identifier, profile)
        self.disconnect_cycling_sensors()
        self.config.set_sensor(
            role,
            self.config.SENSOR_PROTOCOL_BLE,
            identifier,
            profile,
            name,
        )
        self.config.setting.write_config()
        self.connect_cycling_sensors()

    def _select_pairing_profile(
        self,
        role: str,
        identifier: str,
        profile: str | None,
    ) -> str | None:
        if role == "HR":
            return PROFILE_HRS
        if role == "SPD":
            return PROFILE_CSCS
        if role == "PWR":
            return PROFILE_CPS
        if profile in (PROFILE_CSCS, PROFILE_CPS):
            return profile
        profiles = self._cycling_discovered_profiles.get(identifier, ())
        if len(profiles) == 1:
            return profiles[0]
        if (
            PROFILE_CPS in profiles
            and self.config.sensor_uses("PWR", self.config.SENSOR_PROTOCOL_BLE)
            and str(self.config.G_SENSORS["PWR"]["ID"]) == identifier
        ):
            return PROFILE_CPS
        if PROFILE_CSCS in profiles:
            return PROFILE_CSCS
        if PROFILE_CPS in profiles:
            return PROFILE_CPS
        return None

    def remove_cycling_sensor(self, role: str) -> None:
        if role not in self.CYCLING_ROLES:
            return
        self.disconnect_cycling_sensors()
        if self.config.sensor_uses(role, self.config.SENSOR_PROTOCOL_BLE):
            self.config.clear_sensor(role)
        self.config.setting.write_config()
        self.connect_cycling_sensors()

    def _configured_cycling_roles(self) -> dict[str, list[str]]:
        roles_by_identifier = {}
        for role in self.CYCLING_ROLES:
            if not self.is_sensor_available(role):
                continue
            identifier = str(self.config.G_SENSORS[role]["ID"])
            roles_by_identifier.setdefault(identifier, []).append(role)
        return roles_by_identifier

    def connect_cycling_sensors(self) -> bool:
        roles_by_identifier = self._configured_cycling_roles()
        if not roles_by_identifier or self._fake_trainer_session_active:
            return False
        adapter = self._resolve_sensor_adapter()
        if sys.platform.startswith("linux") and adapter is None:
            return False
        started = False
        for identifier, roles in roles_by_identifier.items():
            if self._is_cycling_session_running(identifier):
                continue
            stop_event = asyncio.Event()
            session = BleCyclingSession(
                identifier,
                heart_rate_processor=(
                    self._hrs_heart_rate_processor if "HR" in roles else None
                ),
                speed_processor=(self._csc_speed_processor if "SPD" in roles else None),
                cadence_processor=(
                    self._csc_cadence_processor if "CDC" in roles else None
                ),
                power_processor=(self._cps_power_processor if "PWR" in roles else None),
                cadence_profile=self._configured_cadence_profile(identifier, roles),
                adapter=adapter,
                initial_device=self._cycling_discovered_devices.pop(identifier, None),
                name=self._configured_cycling_name(roles),
                on_name=lambda name, sensor_id=identifier: self._set_cycling_sensor_name(
                    sensor_id, name
                ),
                should_accumulate=lambda: self.config.G_MANUAL_STATUS == "START",
                log=lambda message: app_logger.info(f"[BLE-CYCLING] {message}"),
                debug_log=lambda message: app_logger.debug(f"[BLE-CYCLING] {message}"),
            )
            self._cycling_stop_events[identifier] = stop_event
            self._cycling_session_roles[identifier] = tuple(roles)
            self._cycling_tasks[identifier] = asyncio.create_task(
                session.run(stop_event)
            )
            started = True
        return started or bool(self._cycling_tasks)

    def _configured_cadence_profile(
        self,
        identifier: str,
        roles: list[str],
    ) -> str | None:
        if "CDC" not in roles:
            return None
        profile = self.config.G_SENSORS["CDC"]["TYPE"]
        if profile in (PROFILE_CSCS, PROFILE_CPS):
            return profile
        if "PWR" in roles and "SPD" not in roles:
            return PROFILE_CPS
        if "SPD" in roles and "PWR" not in roles:
            return PROFILE_CSCS
        return None

    def disconnect_cycling_sensors(self) -> None:
        for stop_event in self._cycling_stop_events.values():
            stop_event.set()
        for task in self._cycling_tasks.values():
            task.cancel()
        self._cycling_stop_events.clear()
        self._cycling_tasks.clear()
        self._cycling_session_roles.clear()
        for processor in self._cycling_processors.values():
            if processor is not None:
                processor.set_suspended()
        self._publish_cycling_values()

    def _is_cycling_session_running(self, identifier: str) -> bool:
        if identifier not in self._cycling_tasks:
            return False
        stop_event = self._cycling_stop_events[identifier]
        task = self._cycling_tasks[identifier]
        return not stop_event.is_set() and not task.done()

    def is_cycling_sensor_running(self, role: str | None = None) -> bool:
        for identifier, roles in self._cycling_session_roles.items():
            if role is not None and role not in roles:
                continue
            if self._is_cycling_session_running(identifier):
                return True
        return False

    def _configured_cycling_name(self, roles: list[str]) -> str:
        for role in roles:
            name = str(self.config.G_SENSORS[role]["NAME"] or "").strip()
            if name:
                return name
        return ""

    def _resolve_sensor_adapter(self) -> str | None:
        if not sys.platform.startswith("linux"):
            return None
        errors = []
        resolver = BleAdapterResolver()
        for configured_policy in self.config.get_ble_sensor_adapter_policies():
            try:
                policy = BleAdapterPolicy(configured_policy)
                adapter = resolver.resolve(policy)
                app_logger.debug(f"[BLE-CYCLING] using BlueZ adapter {adapter}")
                return adapter
            except (ValueError, BleAdapterResolutionError) as exc:
                errors.append(str(exc))
        if errors:
            app_logger.warning(
                f"[BLE-CYCLING] adapter resolution failed: {'; '.join(errors)}"
            )
        return None

    def _set_cycling_sensor_name(self, identifier: str, name: str | None) -> None:
        name = str(name or "").strip()
        if not name:
            return
        for role in self.CYCLING_ROLES:
            sensor = self.config.G_SENSORS[role]
            if (
                self.config.sensor_uses(role, self.config.SENSOR_PROTOCOL_BLE)
                and str(sensor["ID"]) == identifier
            ):
                sensor["NAME"] = name

    def connect_zwift_click_v2(self) -> bool:
        """Start Zwift Click V2 listener if it is enabled and available."""
        if not self._is_zwift_click_v2_enabled():
            return False

        # Reset the stop event to allow re-start after a previous stop.
        self._reset_zwift_click_v2_runtime()
        self._zwift_click_v2_task = asyncio.create_task(
            self._run_zwift_click_v2_listener()
        )
        return True

    def disconnect_zwift_click_v2(self) -> None:
        """Stop Zwift Click V2 listener if running."""
        if self._zwift_click_v2_stop_event is not None:
            self._zwift_click_v2_stop_event.set()
        if self._zwift_click_v2_task is not None:
            self._zwift_click_v2_task.cancel()

    def _is_zwift_click_v2_enabled(self) -> bool:
        cfg = self.config.G_ZWIFT_CLICK_V2
        if not cfg["STATUS"]:
            return False
        if not _HAS_ZWIFT_CLICK_V2:
            return False
        return True

    async def _run_zwift_click_v2_listener(self) -> None:
        cfg = self.config.G_ZWIFT_CLICK_V2
        preferred_address = str(cfg["ADDRESS"]).strip()
        button_hard = "Zwift_Click_V2"

        def normalize_button_key(button: str) -> str:
            """Normalize zwift_click_v2 button names into Button_Config keys."""
            if not button:
                return ""
            snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", button)
            snake = re.sub(r"[^A-Za-z0-9]+", "_", snake)
            return snake.upper().strip("_")

        def log(msg: str) -> None:
            app_logger.info(f"[ZwiftClickV2] {msg}")

        def debug_log(msg: str) -> None:
            app_logger.debug(f"[ZwiftClickV2] {msg}")

        def on_classified(side: str, button: str, kind: str, duration: float) -> None:
            button_key = normalize_button_key(button)
            if not button_key:
                return

            index = 1 if kind == "long" else 0

            try:
                loop = self.config.loop
            except Exception:
                loop = None
            if loop and loop.is_running():
                loop.call_soon_threadsafe(
                    self.config.button_config.press_button,
                    button_hard,
                    button_key,
                    index,
                )
                return

            self.config.button_config.press_button(button_hard, button_key, index)

        def on_connected(side: str, address: str, _name: Optional[str]) -> None:
            if not address:
                return
            if cfg["ADDRESS"] == address:
                return
            cfg["ADDRESS"] = address
            setting = self.config.setting
            if setting is not None:
                setting.write_config()

        def on_stopped(_side: str, _packet: bytes) -> None:
            self._notify_zwift_click_v2_stopped()

        adapter = None
        if sys.platform.startswith("linux"):
            try:
                adapter = BleAdapterResolver().resolve(BleAdapterPolicy.BUILTIN)
                debug_log(f"using BlueZ adapter {adapter}")
            except BleAdapterResolutionError as exc:
                log(f"built-in adapter resolution failed: {exc}")
                return

        try:
            await zwift_click_v2.listen(
                on_classified=on_classified,
                stop_event=self._zwift_click_v2_stop_event,
                scan_forever=True,
                preferred_address=preferred_address or None,
                on_connected=on_connected,
                on_stopped=on_stopped,
                log=log,
                debug_log=debug_log,
                adapter=adapter,
                health=self._zwift_click_v2_health,
            )
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE errors are runtime
            log(f"listener crashed: {exc}")

    def _notify_zwift_click_v2_stopped(self) -> None:
        gui = self.config.gui
        if gui is None:
            return

        def show() -> None:
            gui.show_dialog(
                gui.toggle_fake_trainer,
                "Click V2 is locked. Start Fake Trainer to reconnect?",
            )

        self.config.loop.call_soon_threadsafe(show)

    def is_fake_trainer_running(self) -> bool:
        proc = self._fake_trainer_proc
        return proc is not None and proc.poll() is None

    def is_zwift_click_v2_running(self) -> bool:
        if self._zwift_click_v2_stop_event is None or self._zwift_click_v2_task is None:
            return False
        if self._zwift_click_v2_stop_event.is_set():
            return False
        return not self._zwift_click_v2_task.done()

    def _pause_zwift_click_v2_for_fake_trainer(self) -> None:
        if self.is_zwift_click_v2_running():
            self.disconnect_zwift_click_v2()
            self._zwift_click_v2_paused_for_fake_trainer = True
        else:
            self._zwift_click_v2_paused_for_fake_trainer = False

    def _resume_zwift_click_v2_after_fake_trainer(self) -> None:
        if not self._zwift_click_v2_paused_for_fake_trainer:
            return
        self._zwift_click_v2_paused_for_fake_trainer = False
        self.connect_zwift_click_v2()

    def _pause_cycling_sensors_for_fake_trainer(self) -> None:
        if self.is_cycling_sensor_running():
            self.disconnect_cycling_sensors()
            self._cycling_paused_for_fake_trainer = True
        else:
            self._cycling_paused_for_fake_trainer = False

    def _resume_cycling_sensors_after_fake_trainer(self) -> None:
        if not self._cycling_paused_for_fake_trainer:
            return
        self._cycling_paused_for_fake_trainer = False
        self.connect_cycling_sensors()

    def _pause_ble_sensors_for_fake_trainer(self) -> None:
        self._pause_cycling_sensors_for_fake_trainer()
        self._pause_zwift_click_v2_for_fake_trainer()

    def _resume_ble_sensors_after_fake_trainer(self) -> None:
        self._resume_cycling_sensors_after_fake_trainer()
        self._resume_zwift_click_v2_after_fake_trainer()

    def start_fake_trainer_session(self) -> bool:
        if self._fake_trainer_session_active and self.is_fake_trainer_running():
            return True
        if self.is_fake_trainer_running():
            app_logger.warning(
                "Fake trainer session start skipped: fake trainer already running"
            )
            return False

        if not self.start_fake_trainer():
            return False

        self._fake_trainer_session_active = True
        self._pause_ble_sensors_for_fake_trainer()
        return True

    def finish_fake_trainer_session(self) -> bool:
        if not self._fake_trainer_session_active:
            return False

        self._fake_trainer_session_active = False
        self.stop_fake_trainer()
        self._resume_ble_sensors_after_fake_trainer()
        return True

    def toggle_fake_trainer(self) -> bool:
        if self._fake_trainer_session_active:
            self.finish_fake_trainer_session()
            return self.is_fake_trainer_running()
        if self.is_fake_trainer_running():
            self.stop_fake_trainer()
            self._resume_ble_sensors_after_fake_trainer()
        else:
            self._fake_trainer_session_active = False
            started = self.start_fake_trainer()
            if started:
                self._pause_ble_sensors_for_fake_trainer()
        return self.is_fake_trainer_running()

    def start_fake_trainer(self) -> bool:
        if self.is_fake_trainer_running():
            return True

        fake_trainer_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "ble",
                "fake_trainer.py",
            )
        )
        if not os.path.isfile(fake_trainer_path):
            app_logger.warning(f"Fake trainer not found: {fake_trainer_path}")
            return False

        try:
            self._fake_trainer_proc = start_process(
                [sys.executable, fake_trainer_path],
                cmd_print=False,
            )
        except Exception as exc:
            app_logger.warning(f"Fake trainer start failed: {exc}")
            self._fake_trainer_proc = None
            return False

        if self._fake_trainer_proc.poll() is not None:
            app_logger.warning("Fake trainer start failed: process exited early")
            self._fake_trainer_proc = None
            return False

        self._schedule_fake_trainer_check()
        app_logger.info("Fake trainer started")
        return True

    def _schedule_fake_trainer_check(self) -> None:
        try:
            loop = self.config.loop
        except Exception:
            loop = None
        if loop and loop.is_running():
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None
            if running_loop is loop:
                loop.call_later(0.2, self._check_fake_trainer_process)
            else:
                loop.call_soon_threadsafe(
                    loop.call_later,
                    0.2,
                    self._check_fake_trainer_process,
                )
            return
        try:
            import threading
        except Exception:
            return
        timer = threading.Timer(0.2, self._check_fake_trainer_process)
        timer.daemon = True
        self._fake_trainer_check_handle = timer
        timer.start()

    def _check_fake_trainer_process(self) -> None:
        if self.is_fake_trainer_running():
            return
        self._fake_trainer_proc = None
        app_logger.warning("Fake trainer stopped unexpectedly")

    def stop_fake_trainer(self) -> None:
        proc = self._fake_trainer_proc
        if proc is None:
            return
        if proc.poll() is not None:
            self._fake_trainer_proc = None
            return

        try:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=1.0)
        except Exception:
            pass

        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                pass

        if proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=1.0)
            except Exception:
                pass

        self._fake_trainer_proc = None
        app_logger.info("Fake trainer stopped")
