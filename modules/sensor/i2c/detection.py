def i2c_addr_present(addr: int, bus: int = 1) -> bool:
    """Return True if the I2C address responds on the given bus.

    This is a best-effort check intended to prevent runtime Cython builds
    (pyximport) when the hardware is not present.
    """
    try:
        import smbus2
    except ImportError:
        return False

    try:
        with smbus2.SMBus(bus) as i2c:
            try:
                i2c.read_byte(addr)
            except Exception:
                # Fallback for devices that don't support "read byte" without a register.
                i2c.read_byte_data(addr, 0x00)
        return True
    except Exception:
        return False

