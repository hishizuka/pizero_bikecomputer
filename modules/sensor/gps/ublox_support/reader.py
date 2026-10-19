"""Validate UBX frames while avoiding unused satellite and navigation fields."""

from dataclasses import dataclass
from typing import ClassVar

from pyubx2 import GET, VALCKSUM, UBXParseError, UBXReader
from pyubx2.ubxhelpers import calc_checksum

G_NAV_SAT_HEADER = b"\xb5\x62\x01\x35"
G_RXM_SFRBX_HEADER = b"\xb5\x62\x02\x13"


@dataclass(frozen=True, slots=True)
class NavSatSummary:
    num_svs: int
    used_svs: int
    identity: ClassVar[str] = "NAV-SAT"


@dataclass(frozen=True, slots=True)
class SfrbxHeader:
    gnssId: int
    svId: int
    sigId: int
    numWords: int
    identity: ClassVar[str] = "RXM-SFRBX"


def parse_sfrbx_header(message, validate=VALCKSUM):
    if len(message) < 16 or message[:4] != G_RXM_SFRBX_HEADER:
        raise UBXParseError("Incomplete RXM-SFRBX frame")
    payload_size = int.from_bytes(message[4:6], "little")
    if len(message) != payload_size + 8 or payload_size != 8 + 4 * message[10]:
        raise UBXParseError("RXM-SFRBX length or word count mismatch")
    if validate & VALCKSUM and calc_checksum(message[2:-2]) != message[-2:]:
        raise UBXParseError("RXM-SFRBX checksum mismatch")
    return SfrbxHeader(message[6], message[7], message[8], message[10])


def parse_nav_sat(message, validate=VALCKSUM):
    if len(message) < 16 or message[:4] != G_NAV_SAT_HEADER:
        raise UBXParseError("Incomplete NAV-SAT frame")
    payload_size = int.from_bytes(message[4:6], "little")
    if len(message) != payload_size + 8 or payload_size != 8 + 12 * message[11]:
        raise UBXParseError("NAV-SAT length or satellite count mismatch")
    if message[10] != 1:
        raise UBXParseError(f"Unsupported NAV-SAT version {message[10]}")
    if validate & VALCKSUM and calc_checksum(message[2:-2]) != message[-2:]:
        raise UBXParseError("NAV-SAT checksum mismatch")
    # Each 12-byte satellite record has svUsed in bit 3 of its flags word.
    used = sum((flags >> 3) & 1 for flags in message[22:-2:12])
    return NavSatSummary(message[11], used)


class UBloxReader(UBXReader):
    @staticmethod
    def parse(message, msgmode=GET, validate=VALCKSUM, parsebitfield=1):
        if msgmode == GET and message[:4] == G_NAV_SAT_HEADER:
            return parse_nav_sat(message, validate)
        if (
            msgmode == GET
            and message[:4] == G_RXM_SFRBX_HEADER
            and len(message) >= 16
            and message[12] == 2
            and (message[6], message[8]) != (5, 1)
        ):
            # Preserve full QZSS L1S parsing and the existing handling of other versions.
            return parse_sfrbx_header(message, validate)
        return UBXReader.parse(
            message, msgmode=msgmode, validate=validate, parsebitfield=parsebitfield
        )
