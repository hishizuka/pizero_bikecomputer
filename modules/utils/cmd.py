import subprocess

from logger import app_logger


# still return returncode
def exec_cmd(cmd, cmd_print=True, timeout=None):
    if cmd_print:
        app_logger.info(cmd)
    try:
        return subprocess.run(cmd, timeout=timeout).returncode
    except Exception:  # noqa
        app_logger.exception(f"Failed executing {cmd}")


def exec_cmd_return_value(cmd, cmd_print=True, timeout=None):
    if cmd_print:
        app_logger.info(cmd)
    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        string = p.stdout.decode("utf8").strip()
        return string
    except subprocess.TimeoutExpired:
        app_logger.exception(f"Timeout {cmd}")
    except Exception:  # noqa
        app_logger.exception(f"Failed executing {cmd}")


def is_service_running(service):
    return not exec_cmd(["systemctl", "is-active", "--quiet", service], cmd_print=False)


# TODO we might want to compare pid, because it might be running as a service AND manually
def is_running_as_service():
    return is_service_running("pizero_bikecomputer")
