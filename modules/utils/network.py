import socket


def detect_network():
    try:
        socket.setdefaulttimeout(3)
        connect_interface = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connect_interface.connect(("8.8.8.8", 53))
        return connect_interface.getsockname()[0]
    except socket.error:
        return False
