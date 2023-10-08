FROM python:3.11.6-slim-bookworm

RUN apt update
RUN apt install -y gcc git libsqlite3-dev python3-pyqt5 sqlite3

WORKDIR /opt

COPY ./reqs/full.txt .
RUN python -m pip install -r full.txt
# still needed
RUN python -m pip install PyQt5

ENTRYPOINT ["python", "pizero_bikecomputer.py"]