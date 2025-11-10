import logging


app_logger = logging.getLogger("pizero_bikecomputer")
app_logger.setLevel(level=logging.INFO)

sh = logging.StreamHandler()

# If the output is to systemd logs, the timestamp is unnecessary.
#formatter = logging.Formatter("%(levelname)s: %(message)s")
formatter = logging.Formatter(
    fmt="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
sh.setFormatter(formatter)

app_logger.addHandler(sh)
