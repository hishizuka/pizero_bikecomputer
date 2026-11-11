"""Shared connections for devices used by sensors, displays and controls."""

from typing import TYPE_CHECKING

from modules.board_config import BoardType

from .bridge_core import Bridge

if TYPE_CHECKING:
    from modules.config import Config


def create_bridge(config: "Config") -> Bridge | None:
    # Keep display-only CardputerZero configurations working.
    if config.G_BOARD_TYPE == BoardType.CARDPUTERZERO or config.G_DISPLAY == "CardputerZero":
        from .bridge_cardputerzero import CardputerZeroBridge

        return CardputerZeroBridge(config)
    return None


__all__ = ["Bridge", "create_bridge"]
