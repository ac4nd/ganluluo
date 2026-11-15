"""外联 HTTP 防护：仅 http/https；解析全部地址，拒绝环回/私有/保留段。"""
import ipaddress
import socket
from urllib.parse import urlparse


def assert_safe_external_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"仅允许 http/https: {parsed.scheme}")
    host = parsed.hostname
    if not host:
        raise ValueError("URL 缺少主机名")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ValueError(f"无法解析主机: {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f"禁止访问内网/保留地址: {ip}")
