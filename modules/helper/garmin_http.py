"""IPv4 transport for Garmin's requests-based APIs and token refresh."""

import socket
import sys
from functools import partial

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import (
    ConnectTimeoutError,
    NameResolutionError,
    NewConnectionError,
)
from urllib3.util import Timeout


class _IPv4Connection:
    def _new_conn(self):
        # Keep self.host unchanged for TLS SNI and certificate verification.
        sock = None
        error = None
        try:
            addresses = socket.getaddrinfo(
                self._dns_host, self.port, socket.AF_INET, socket.SOCK_STREAM
            )
            for family, socktype, protocol, _, address in addresses:
                try:
                    sock = socket.socket(family, socktype, protocol)
                    for option in self.socket_options or ():
                        sock.setsockopt(*option)
                    if self.timeout is not Timeout.DEFAULT_TIMEOUT:
                        sock.settimeout(self.timeout)
                    if self.source_address:
                        sock.bind(self.source_address)
                    sock.connect(address)
                    break
                except OSError as exc:
                    error = exc
                    if sock is not None:
                        sock.close()
                    sock = None
            if sock is None:
                raise error or OSError("getaddrinfo returned no IPv4 addresses")
        except socket.gaierror as exc:
            raise NameResolutionError(self.host, self, exc) from exc
        except socket.timeout as exc:
            raise ConnectTimeoutError(
                self,
                f"Connection to {self.host} timed out. "
                f"(connect timeout={self.timeout})",
            ) from exc
        except OSError as exc:
            raise NewConnectionError(
                self, f"Failed to establish a new connection: {exc}"
            ) from exc
        sys.audit("http.client.connect", self, self.host, self.port)
        return sock


class _IPv4HTTPConnection(_IPv4Connection, HTTPConnection):
    pass


class _IPv4HTTPSConnection(_IPv4Connection, HTTPSConnection):
    pass


class _IPv4HTTPPool(HTTPConnectionPool):
    ConnectionCls = _IPv4HTTPConnection


class _IPv4HTTPSPool(HTTPSConnectionPool):
    ConnectionCls = _IPv4HTTPSConnection


def _configure_pool_manager(manager):
    # urllib3's default scheme mapping is shared between pool managers.
    manager.pool_classes_by_scheme = {
        "http": _IPv4HTTPPool,
        "https": _IPv4HTTPSPool,
    }


class _IPv4Adapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        _configure_pool_manager(self.poolmanager)

    def proxy_manager_for(self, proxy, **kwargs):
        if proxy.lower().startswith("socks"):
            raise requests.exceptions.InvalidSchema(
                "Garmin IPv4 transport requires an HTTP or HTTPS proxy."
            )
        manager = super().proxy_manager_for(proxy, **kwargs)
        _configure_pool_manager(manager)
        return manager


def _configure_session(session, *, ipv6):
    if not ipv6:
        adapter = _IPv4Adapter()
        session.mount("http://", adapter)
        session.mount("https://", adapter)


def request(method, url, *, ipv6, **kwargs):
    with requests.Session() as session:
        _configure_session(session, ipv6=ipv6)
        return session.request(method, url, **kwargs)


def _auth_post(original_post, url, *, ipv6, **kwargs):
    from garminconnect.client import HAS_CFFI

    if not HAS_CFFI:
        return request("POST", url, ipv6=ipv6, **kwargs)
    if not ipv6:
        from curl_cffi.const import CurlIpResolve, CurlOpt

        kwargs["curl_options"] = dict(kwargs.get("curl_options", {}))
        kwargs["curl_options"][CurlOpt.IPRESOLVE] = CurlIpResolve.V4
    return original_post(url, **kwargs)


def configure_garmin_client(garmin, *, ipv6):
    """Configure tokenstore login, API calls, and DI token refresh per client."""
    client = garmin.client
    for session in (client._api_session, client.cs):
        _configure_session(session, ipv6=ipv6)
    client._http_post = partial(_auth_post, client._http_post, ipv6=ipv6)
