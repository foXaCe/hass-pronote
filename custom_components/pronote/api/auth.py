"""Gestion de l'authentification Pronote avec refresh token."""

from __future__ import annotations

import asyncio
import builtins
import json
import logging
import re
from typing import TYPE_CHECKING, Any

import pronotepy
from pronotepy import CryptoError, ENTLoginError, QRCodeDecryptError

from ..const import DEFAULT_DEVICE_NAME
from .exceptions import (
    AuthenticationError,
    ConnectionError,
    InvalidResponseError,
    IPSuspendedError,
    QRCodeRejectedError,
)
from .models import Credentials

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Timeouts pour les opérations d'auth
AUTH_TIMEOUT = 30
CONNECT_TIMEOUT = 10


def _account_pin(data: dict[str, Any]) -> str | None:
    """PIN à présenter quand Pronote redemande la double authentification.

    Pronote peut exiger une nouvelle validation de l'appareil plusieurs jours
    après l'appairage. Sans PIN, pronotepy lève MFAError et le jeton devient
    inutilisable. Le PIN du QR code est le même que celui de l'espace mobile,
    on s'en sert donc par défaut.
    """
    return data.get("account_pin") or data.get("qr_code_pin") or None


def _raise_if_malformed_response(err: Exception) -> None:
    """Tell a broken server answer apart from a refused token.

    pronotepy indexes the server payload directly (``response_data["dataSec"]``
    in pronoteAPI), so an answer that is not the expected shape surfaces as a
    bare KeyError or TypeError. Wrapped as an authentication failure, it told
    users their token had expired and sent them burning QR codes over a
    problem that has nothing to do with credentials — and that a later refresh
    may well recover from on its own.
    """
    if isinstance(err, KeyError | TypeError | IndexError):
        raise InvalidResponseError(
            f"Réponse inattendue de Pronote (champ {err} manquant) — le serveur a mal répondu, "
            "les identifiants ne sont pas en cause"
        ) from err


def _raise_if_ip_suspended(err: Exception) -> None:
    """Turn Pronote's IP ban into a retryable error, not a credentials problem.

    pronotepy raises a plain PronoteAPIError("Your IP address is suspended.")
    from the login page. Wrapped as an authentication failure, it asked the
    user for a new QR code, so they retried, so the ban lasted longer.
    """
    if "ip address is suspended" in str(err).lower():
        raise IPSuspendedError(
            "Pronote a suspendu cette adresse IP après trop de tentatives de connexion. Attendez avant de réessayer."
        ) from err


def _check_logged_in(client: Any, message: str) -> None:
    """Refuse a client pronotepy built but never logged in.

    ``Client.__init__`` stores the outcome in ``logged_in`` instead of raising,
    so a wrong PIN or a spent QR code used to travel on as a working client and
    blow up later on ``client.info``, as an unrelated "Unknown error".
    """
    if getattr(client, "logged_in", True):
        return
    _LOGGER.debug("Pronote a rejeté la connexion: %s", message)
    raise QRCodeRejectedError(message)


def _device_name(data: dict[str, Any]) -> str:
    """Nom d'appareil envoyé lors d'un ré-enregistrement demandé par Pronote."""
    return data.get("device_name") or DEFAULT_DEVICE_NAME


class PronoteAuth:
    """Gestionnaire d'authentification Pronote."""

    def __init__(self, hass: HomeAssistant | None = None) -> None:
        """Initialize le gestionnaire d'authentification."""
        self.hass = hass

    async def authenticate(
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
            # Exécuter les appels bloquants dans un thread séparé
            if connection_type == "qrcode":
                client, creds = await asyncio.to_thread(self._auth_qrcode, config_data, account_type)
            else:
                client, creds = await asyncio.to_thread(self._auth_username_password, config_data, account_type)
        except (CryptoError, QRCodeDecryptError) as err:
            raise AuthenticationError(f"Cryptographie/QR code invalide: {err}") from err
        except ENTLoginError as err:
            raise AuthenticationError(f"Échec login ENT: {err}") from err
        except ConnectionError as err:
            raise ConnectionError(f"Erreur réseau: {err}") from err
        except builtins.ConnectionError as err:
            raise ConnectionError(f"Erreur réseau: {err}") from err
        except (AuthenticationError, IPSuspendedError, InvalidResponseError):
            # Already typed by the login helpers; re-wrapping would hide the
            # subclass the config flow uses to pick its error message.
            raise
        except Exception as err:
            _raise_if_ip_suspended(err)
            # Log avec plus de détails pour debug (sans exposer de secrets)
            _LOGGER.error("Échec authentification Pronote: %s - %s", type(err).__name__, str(err))
            raise AuthenticationError(f"Authentification impossible: {err}") from err

        if client is None:
            raise AuthenticationError("Client Pronote non créé")

        # No session_check here on purpose: the session was just opened, and a
        # failing check makes pronotepy run refresh(), i.e. a second full
        # login. Pronote counts logins for its brute-force protection and
        # suspends the IP address, so the free check was not free at all.
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
            client_class = pronotepy.ParentClient if account_type == "parent" else pronotepy.Client
            client = client_class(
                pronote_url=url,
                username=data["username"],
                password=data["password"],
                account_pin=_account_pin(data),
                device_name=_device_name(data),
                client_identifier=data.get("client_identifier"),
                ent=ent,
            )
        except Exception as err:
            _raise_if_ip_suspended(err)
            _raise_if_malformed_response(err)
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
        """Authentification par QR code ou par jeton enregistré.

        A fresh QR code wins over the stored token: providing one is how the
        user asks to start over, and the token may well be the dead one that
        sent them looking for a QR code in the first place. The other way round
        then serves as the fallback.
        """
        client_class = pronotepy.ParentClient if account_type == "parent" else pronotepy.Client
        has_qr = bool(data.get("qr_code_json"))
        has_token = bool(data.get("qr_code_url")) and bool(data.get("qr_code_username"))

        if has_qr:
            try:
                return self._login_with_qrcode(client_class, data)
            except AuthenticationError:
                if not has_token:
                    raise
                _LOGGER.debug("QR code refusé, essai avec le jeton enregistré")

        if not has_token:
            _LOGGER.error("Aucun QR code JSON dans les données: %s", list(data.keys()))
            raise AuthenticationError("Aucun QR code ou token sauvegardé")

        return self._login_with_token(client_class, data)

    def _login_with_token(
        self,
        client_class: type,
        data: dict[str, Any],
    ) -> tuple[pronotepy.Client | pronotepy.ParentClient, Credentials]:
        """Reconnexion avec le jeton renvoyé par la connexion précédente."""
        _LOGGER.debug("Utilisation token_login pour: %s", data["qr_code_username"])
        try:
            client = client_class.token_login(
                pronote_url=data["qr_code_url"],
                username=data["qr_code_username"],
                password=data["qr_code_password"],
                uuid=data.get("qr_code_uuid"),
                account_pin=_account_pin(data),
                device_name=_device_name(data),
                client_identifier=data.get("client_identifier"),
            )
            _check_logged_in(client, "Jeton Pronote refusé, il faut un nouveau QR code")
        except AuthenticationError:
            raise
        except Exception as err:
            _raise_if_ip_suspended(err)
            _raise_if_malformed_response(err)
            _LOGGER.debug("Token login échoué: %s - %s", type(err).__name__, err)
            raise AuthenticationError(
                f"Token expiré, veuillez reconfigurer l'intégration avec un nouveau QR code: {err}"
            ) from err

        exported = client.export_credentials()
        _LOGGER.debug("Pronote token_login succeeded, new credentials exported")
        credentials = Credentials(
            pronote_url=exported.get("pronote_url", data["qr_code_url"]),
            username=exported.get("username", data["qr_code_username"]),
            password=exported.get("password", data.get("qr_code_password", "")),
            uuid=exported.get("uuid", data.get("qr_code_uuid")),
            client_identifier=exported.get("client_identifier", data.get("client_identifier")),
        )
        return client, credentials

    def _login_with_qrcode(
        self,
        client_class: type,
        data: dict[str, Any],
    ) -> tuple[pronotepy.Client | pronotepy.ParentClient, Credentials]:
        """Première connexion, à partir du QR code affiché par Pronote."""
        _LOGGER.debug("Utilisation qrcode_login (première fois)")
        try:
            qr_code_json = json.loads(data["qr_code_json"])
        except json.JSONDecodeError as err:
            _LOGGER.error("JSONDecodeError: %s", err)
            raise InvalidResponseError(f"QR code JSON invalide: {err}") from err

        _LOGGER.debug("QR code JSON parsé avec succès, URL: %s", qr_code_json.get("url", "N/A"))
        try:
            # skip_2fa: after a successful login, pronotepy probes
            # PageInfosPerso (tab 49) just to detect whether 2FA is on. Schools
            # that deny that tab answer "3 | Accès refusé", which surfaced as an
            # authentication failure although the login itself had worked. The
            # probe is not needed here: account_pin and device_name are passed
            # to every login, so pronotepy answers the two-factor check when
            # Pronote actually asks for it.
            client = client_class.qrcode_login(
                qr_code=qr_code_json,
                pin=data["qr_code_pin"],
                uuid=data["qr_code_uuid"],
                account_pin=_account_pin(data),
                client_identifier=data.get("client_identifier"),
                device_name=_device_name(data),
                skip_2fa=True,
            )
            _check_logged_in(
                client,
                "Pronote a refusé ce QR code : PIN incorrect, ou QR code expiré ou déjà utilisé "
                "(il n'est valable que dix minutes, et une seule fois)",
            )
        except AuthenticationError:
            raise
        except Exception as err:
            _raise_if_ip_suspended(err)
            _raise_if_malformed_response(err)
            _LOGGER.error("Exception dans qrcode_login: %s - %s", type(err).__name__, err)
            raise AuthenticationError(f"QR code login échoué: {err}") from err

        _LOGGER.debug("qrcode_login réussi, client créé")
        exported = client.export_credentials()
        credentials = Credentials(
            pronote_url=exported.get("pronote_url", ""),
            username=exported.get("username", ""),
            password=exported.get("password", ""),
            uuid=exported.get("uuid"),
            client_identifier=exported.get("client_identifier"),
        )
        return client, credentials

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
