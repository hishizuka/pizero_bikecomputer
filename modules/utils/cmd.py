import subprocess

from logger import app_logger


# still return returncode
def exec_cmd(cmd, cmd_print=True):
    if cmd_print:
        app_logger.info(cmd)
    try:
        return subprocess.run(cmd).returncode
    except Exception:  # noqa
        app_logger.exception(f"Failed executing {cmd}")


def exec_cmd_return_value(cmd, cmd_print=True):
    if cmd_print:
        app_logger.info(cmd)
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        string = p.stdout.decode("utf8").strip()
        return string
    except Exception:  # noqa
        app_logger.exception(f"Failed executing {cmd}")


# TODO we might want to compare pid, because it might be running as a service AND manually
def is_running_as_service():
    return not exec_cmd(
        ["sudo", "systemctl", "is-active", "--quiet", "pizero_bikecomputer"]
    )
