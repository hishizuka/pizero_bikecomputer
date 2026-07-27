from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping


class BoardType(StrEnum):
    AUTO = "auto"
    PIZERO_BIKECOMPUTER = "pizero_bikecomputer"
    BRYTON_RIDER_S800 = "bryton_rider_s800"


class ButtonTemplate(StrEnum):
    FIVE_BUTTON = "5_BUTTON"
    FOUR_BUTTON = "4_BUTTON"
    THREE_BUTTON = "3_BUTTON"
    TWO_BUTTON = "2_BUTTON"


class I2CDevice(StrEnum):
    BHI3 = "bhi3"
    VCNL4040 = "vcnl4040"
    LTR308ALS = "ltr308als"
    BMP581 = "bmp581"
    BMI270 = "bmi270"
    BMM150 = "bmm150"


@dataclass(frozen=True)
class I2CSensorChoice:
    candidates: tuple[I2CDevice, ...]
    required: bool = False


@dataclass(frozen=True)
class GPIOButtonPreset:
    template: ButtonTemplate
    pins: Mapping[str, int]
    overrides: Mapping[str, Mapping[str, tuple[str, str]]] | None = None
    pull_up: bool = True


@dataclass(frozen=True)
class IMUAxisPreset:
    axis_swap_xy_status: bool = False
    axis_conversion_status: bool = False
    axis_conversion_coef: tuple[float, float, float] = (1.0, 1.0, 1.0)
    mag_axis_swap_xy_status: bool = False
    mag_axis_conversion_status: bool = False
    mag_axis_conversion_coef: tuple[float, float, float] = (1.0, 1.0, 1.0)


@dataclass(frozen=True)
class DisplayPreset:
    use_backlight: bool = False
    auto_backlight_cutoff: int = 10


@dataclass(frozen=True)
class BoardPreset:
    i2c_sensors: tuple[I2CSensorChoice, ...] | None
    gpio_buttons: GPIOButtonPreset | None = None
    imu_axis: IMUAxisPreset | None = None
    display: DisplayPreset | None = None
    use_buzzer: bool = False
    dual_display_mode: bool = False


BOARD_PRESETS: dict[BoardType, BoardPreset] = {
    BoardType.AUTO: BoardPreset(i2c_sensors=None),
    BoardType.PIZERO_BIKECOMPUTER: BoardPreset(
        i2c_sensors=(
            I2CSensorChoice((I2CDevice.BHI3,), required=True),
            I2CSensorChoice((I2CDevice.VCNL4040,), required=True),
        ),
        gpio_buttons=GPIOButtonPreset(
            template=ButtonTemplate.FIVE_BUTTON,
            pins={"A": 4, "B": 27, "C": 5, "D": 6, "E": 26},
            overrides={
                "MAIN": {
                    "C": ("bhi3_raw_log", "toggle_fake_trainer"),
                },
            },
        ),
        imu_axis=IMUAxisPreset(
            axis_swap_xy_status=True,
            axis_conversion_status=True,
            axis_conversion_coef=(1.0, 1.0, -1.0),
            mag_axis_swap_xy_status=True,
            mag_axis_conversion_status=True,
            mag_axis_conversion_coef=(1.0, 1.0, -1.0),
        ),
        display=DisplayPreset(
            use_backlight=True,
            auto_backlight_cutoff=2,
        ),
        use_buzzer=True,
        dual_display_mode=True,
    ),
    BoardType.BRYTON_RIDER_S800: BoardPreset(
        i2c_sensors=(
            I2CSensorChoice((I2CDevice.BMI270,), required=True),
            I2CSensorChoice((I2CDevice.BMM150,), required=True),
            I2CSensorChoice((I2CDevice.BMP581,), required=True),
            I2CSensorChoice((I2CDevice.LTR308ALS,), required=True),
        ),
        gpio_buttons=GPIOButtonPreset(
            template=ButtonTemplate.FOUR_BUTTON,
            pins={"A": 23, "B": 4, "C": 26, "D": 16},
        ),
        imu_axis=IMUAxisPreset(
            axis_swap_xy_status=False,
            axis_conversion_status=False,
            axis_conversion_coef=(1.0, 1.0, -1.0),
            mag_axis_swap_xy_status=False,
            mag_axis_conversion_status=True,
            mag_axis_conversion_coef=(1.0, -1.0, 1.0),
        ),
        display=DisplayPreset(
            use_backlight=True,
            auto_backlight_cutoff=2,
        ),
        use_buzzer=True,
    ),
}


def get_board_preset(board_type: BoardType | str) -> BoardPreset:
    return BOARD_PRESETS[BoardType(board_type)]
