FROM python:slim-bookworm

RUN apt update
RUN apt install -y build-essential git python3-venv python3-yaml cython3 cmake python3-numpy sqlite3 libsqlite3-dev python3-pil python3-aiohttp python3-aiofiles python3-psutil python3-pyqt6 python3-pyqt6.qtsvg pyqt6-dev-tools

WORKDIR /opt

RUN python -m pip install oyaml polyline qasync pyqtgraph git+https://github.com/hishizuka/crdp.git

ENTRYPOINT ["python", "pizero_bikecomputer.py"]