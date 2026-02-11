"""Gestion de l'authentification Pronote avec refresh token."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

import pronotepy
from pronotepy import CryptoError, ENTLoginError, QRCodeDecryptError

from .exceptions import AuthenticationError, ConnectionError, InvalidResponseError
from .models import Credentials

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Timeouts pour les opérations d'auth
AUTH_TIMEOUT = 30
CONNECT_TIMEOUT = 10


class PronoteAuth:
    """Gestionnaire d'authentification Pronote."""

    def __init__(self, hass: HomeAssistant | None = None) -> None:
        """Initialize le gestionnaire d'authentification."""
        self.hass = hass

    def authenticate(
        self,
        connection_type: str,
        config_data: dict[str, Any],
    ) -> tuple[pronotepy.Client | pronotepy.ParentClient, Credentials]:
        """Authentifie et retourne le client + credentials.

        Args:
            connection_type: 'username_password' ou 'qrcode'
            config_data: Données de configuration

        Returns:
            Tuple (client, credentials)

        Raises:
            AuthenticationError: Si l'authentification échoue
            ConnectionError: Si problème de connexion
        """
        account_type = config_data.get("account_type", "student")

        try:
            if connection_type == "qrcode":
                client, creds = self._auth_qrcode(config_data, account_type)
            else:
                client, creds = self._auth_username_password(config_data, account_type)
        except (CryptoError, QRCodeDecryptError) as err:
            raise AuthenticationError(f"Cryptographie/QR code invalide: {err}") from err
        except ENTLoginError as err:
            raise AuthenticationError(f"Échec login ENT: {err}") from err
        except ConnectionError as err:  # noqa: F821
            raise ConnectionError(f"Erreur réseau: {err}") from err
        except Exception as err:
            # Log sans exposer de potentiels secrets
            _LOGGER.error("Échec authentification Pronote: %s", type(err).__name__)
            raise AuthenticationError(f"Authentification impossible: {err}") from err

        if client is None:
            raise AuthenticationError("Client Pronote non créé")

        # Vérification de session
        try:
            client.session_check()
        except Exception as err:
            _LOGGER.warning("Session check a échoué: %s", type(err).__name__)
            # On continue quand même, pronotepy peut auto-réparer

        return client, creds

    def _auth_username_password(
        self,
        data: dict[str, Any],
        account_type: str,
    ) -> tuple[pronotepy.Client | pronotepy.ParentClient, Credentials]:
        """Authentification par username/password."""
        url = self._normalize_url(data["url"], account_type)
        ent = self._get_ent(data.get("ent"))

        if not ent:
            url += "?login=true"

        try:
            client_class = (
                pronotepy.ParentClient if account_type == "parent" else pronotepy.Client
            )
            client = client_class(
                pronote_url=url,
                username=data["username"],
                password=data["password"],
                account_pin=data.get("account_pin"),
                device_name=data.get("device_name"),
                client_identifier=data.get("client_identifier"),
                ent=ent,
            )
        except Exception as err:
            raise AuthenticationError(f"Login échoué: {err}") from err

        # Nettoyage sécurisé
        if hasattr(client, "account_pin"):
            del client.account_pin

        # Extraction credentials pour refresh
        try:
            exported = client.export_credentials()
            credentials = Credentials(
                pronote_url=exported.get("pronote_url", url),
                username=exported.get("username", data["username"]),
                password=client.password if hasattr(client, "password") else data["password"],
                uuid=exported.get("uuid"),
                client_identifier=exported.get("client_identifier"),
            )
        except Exception as err:
            _LOGGER.debug("Export credentials échoué: %s", err)
            credentials = Credentials(
                pronote_url=url,
                username=data["username"],
                password=data["password"],
            )

        return client, credentials

    def _auth_qrcode(
        self,
        data: dict[str, Any],
        account_type: str,
    ) -> tuple[pronotepy.Client | pronotepy.ParentClient, Credentials]:
        """Authentification par QR code ou token."""
        client_class = (
            pronotepy.ParentClient if account_type == "parent" else pronotepy.Client
        )

        # Préférence: token_login si credentials déjà sauvegardés
        if "qr_code_url" in data and "qr_code_username" in data:
            _LOGGER.debug("Utilisation token_login pour: %s", data["qr_code_username"])
            try:
                client = client_class.token_login(
                    pronote_url=data["qr_code_url"],
                    username=data["qr_code_username"],
                    password=data["qr_code_password"],
                    uuid=data.get("qr_code_uuid"),
                    account_pin=data.get("account_pin"),
                    device_name=data.get("device_name"),
                    client_identifier=data.get("client_identifier"),
                )

                credentials = Credentials(
                    pronote_url=data["qr_code_url"],
                    username=data["qr_code_username"],
                    password=client.password if hasattr(client, "password") else data.get("qr_code_password", ""),
                    uuid=data.get("qr_code_uuid"),
                    client_identifier=data.get("client_identifier"),
                )
                return client, credentials
            except Exception as err:
                _LOGGER.warning("Token login échoué, tentative QR code: %s", err)
                # Continue vers QR code login

        # Premier login avec QR code
        if "qr_code_json" not in data:
            raise AuthenticationError("Aucun QR code ou token sauvegardé")

        _LOGGER.debug("Utilisation qrcode_login (première fois)")
        try:
            qr_code_json = json.loads(data["qr_code_json"])
            client = client_class.qrcode_login(
                qr_code=qr_code_json,
                pin=data["qr_code_pin"],
                uuid=data["qr_code_uuid"],
                account_pin=data.get("account_pin"),
                client_identifier=data.get("client_identifier"),
                device_name=data.get("device_name"),
            )

            # Export credentials pour sauvegarde
            exported = client.export_credentials()
            credentials = Credentials(
                pronote_url=exported.get("pronote_url", ""),
                username=exported.get("username", ""),
                password=client.password if hasattr(client, "password") else "",
                uuid=exported.get("uuid"),
                client_identifier=exported.get("client_identifier"),
            )
            return client, credentials
        except json.JSONDecodeError as err:
            raise InvalidResponseError(f"QR code JSON invalide: {err}") from err
        except Exception as err:
            raise AuthenticationError(f"QR code login échoué: {err}") from err

    def _normalize_url(self, url: str, account_type: str) -> str:
        """Normalise l'URL Pronote."""
        url = re.sub(r"/[^/]+\.html$", "/", url)
        if not url.endswith("/"):
            url += "/"
        suffix = "parent" if account_type == "parent" else "eleve"
        return f"{url}{suffix}.html"

    def _get_ent(self, ent_name: str | None) -> Any:
        """Récupère la classe ENT si spécifiée."""
        if not ent_name:
            return None
        return getattr(pronotepy.ent, ent_name, None)

    def refresh_credentials(
        self,
        client: pronotepy.Client | pronotepy.ParentClient,
    ) -> Credentials | None:
        """Rafraîchit les credentials depuis un client existant.

        Args:
            client: Client Pronote actif

        Returns:
            Nouveaux credentials ou None si échec
        """
        try:
            exported = client.export_credentials()
            return Credentials(
                pronote_url=exported.get("pronote_url", ""),
                username=exported.get("username", ""),
                password=client.password if hasattr(client, "password") else "",
                uuid=exported.get("uuid"),
                client_identifier=exported.get("client_identifier"),
            )
        except Exception as err:
            _LOGGER.debug("Refresh credentials échoué: %s", err)
            return None
