"""Client wrapper for the Pronote integration."""

from __future__ import annotations

import json
import logging
import re

import pronotepy

_LOGGER = logging.getLogger(__name__)


def get_pronote_client(data) -> pronotepy.Client | pronotepy.ParentClient | None:
    _LOGGER.debug("Coordinator uses connection: %s", data["connection_type"])

    if data["connection_type"] == "qrcode":
        client = get_client_from_qr_code(data)
    else:
        client = get_client_from_username_password(data)

    if client is None:
        _LOGGER.warning("Client creation failed")
        return None

    try:
        client.session_check()
    except Exception as e:
        _LOGGER.error("Session check failed: %s", e)

    return client


def get_client_from_username_password(
    data,
) -> pronotepy.Client | pronotepy.ParentClient | None:
    url = data["url"]
    url = re.sub(r"/[^/]+\.html$", "/", url)
    if not url.endswith("/"):
        url += "/"
    url = url + ("parent" if data["account_type"] == "parent" else "eleve") + ".html"

    ent = None
    if "ent" in data:
        ent = getattr(pronotepy.ent, data["ent"])

    if not ent:
        url += "?login=true"

    try:
        client = (pronotepy.ParentClient if data["account_type"] == "parent" else pronotepy.Client)(
            pronote_url=url,
            username=data["username"],
            password=data["password"],
            account_pin=data.get("account_pin", None),
            device_name=data.get("device_name", None),
            client_identifier=data.get("client_identifier", None),
            ent=ent,
        )
        del ent
        del client.account_pin
        _LOGGER.info(client.info.name)
    except Exception as err:
        _LOGGER.error("Failed to create Pronote client: %s", err)
        return None

    return client


def get_client_from_qr_code(data) -> pronotepy.Client | pronotepy.ParentClient | None:
    # Prefer token_login when saved credentials exist (returning user)
    if "qr_code_url" in data and "qr_code_username" in data:
        _LOGGER.debug("Coordinator uses token_login for qr_code_username: %s", data["qr_code_username"])
        return (pronotepy.ParentClient if data["account_type"] == "parent" else pronotepy.Client).token_login(
            pronote_url=data["qr_code_url"],
            username=data["qr_code_username"],
            password=data["qr_code_password"],
            uuid=data["qr_code_uuid"],
            account_pin=data.get("account_pin", None),
            device_name=data.get("device_name", None),
            client_identifier=data.get("client_identifier", None),
        )

    # First-time QR code login
    if "qr_code_json" not in data:
        _LOGGER.error("No QR code credentials found")
        return None

    _LOGGER.debug("Coordinator uses qrcode_login (first time)")
    qr_code_json = json.loads(data["qr_code_json"])
    client = (pronotepy.ParentClient if data["account_type"] == "parent" else pronotepy.Client).qrcode_login(
        qr_code=qr_code_json,
        pin=data["qr_code_pin"],
        uuid=data["qr_code_uuid"],
        account_pin=data.get("account_pin", None),
        client_identifier=data.get("client_identifier", None),
        device_name=data.get("device_name", None),
    )
    return client


def get_day_start_at(lessons):
    day_start_at = None

    if lessons is not None:
        for lesson in lessons:
            if not lesson.canceled:
                day_start_at = lesson.start
                break

    return day_start_at
