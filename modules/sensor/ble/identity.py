def format_ble_identity(
    name: str | None,
    identifier: str,
) -> str:
    """Format BLE identities consistently for UI and logs."""
    device_name = str(name or "").strip()
    device_id = str(identifier or "").strip()
    if device_name and device_id:
        return f"{device_name} ({device_id})"
    return device_name or device_id
