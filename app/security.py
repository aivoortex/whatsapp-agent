import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    pass


def validate_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("Apenas URLs HTTP(S) completas são aceitas.")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URLs com credenciais não são aceitas.")
    if parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
        raise UnsafeUrlError("Endereços locais não são aceitos.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError("Não foi possível resolver o domínio.") from exc
    if any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise UnsafeUrlError("O domínio aponta para uma rede privada ou reservada.")
