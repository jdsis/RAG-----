from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import HTTPException

from app.core.config import settings


def validate_web_url(url: str) -> str:
    return _validate_url(
        url,
        allow_private=settings.allow_private_web_urls,
        allowed_hosts=[],
        purpose="Web import URL",
    )


def validate_model_base_url(url: str) -> str:
    return _validate_url(
        url,
        allow_private=settings.allow_private_model_urls,
        allowed_hosts=settings.allowed_model_hosts,
        purpose="Model Base URL",
    ).rstrip("/")


def _validate_url(url: str, allow_private: bool, allowed_hosts: list[str], purpose: str) -> str:
    value = (url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail=f"{purpose} must be an http(s) URL")

    hostname = parsed.hostname.strip().lower()
    allowed = {host.lower() for host in allowed_hosts}
    if allowed and hostname not in allowed:
        raise HTTPException(status_code=400, detail=f"{purpose} host is not allowed")

    if not allow_private and not _is_allowed_public_host(hostname):
        raise HTTPException(status_code=400, detail=f"{purpose} cannot point to private or local addresses")
    return value


def _is_allowed_public_host(hostname: str) -> bool:
    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    if not addresses:
        return False
    return all(_is_public_ip(item[4][0]) for item in addresses)


def _is_public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )

