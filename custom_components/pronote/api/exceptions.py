"""Exceptions API typées pour l'intégration Pronote."""

from __future__ import annotations


class PronoteAPIError(Exception):
    """Exception de base pour les erreurs API Pronote."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        """Initialize l'exception.

        Args:
            message: Message d'erreur
            retry_after: Délai en secondes avant retry (pour HTTP 429)
        """
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


class AuthenticationError(PronoteAPIError):
    """Échec d'authentification (credentials invalides, token expiré)."""

    pass


class QRCodeRejectedError(AuthenticationError):
    """Pronote a refusé le QR code ou le PIN.

    pronotepy ne lève rien dans ce cas : ``_login`` rend False et le client est
    rendu non connecté, ce qui faisait échouer l'étape suivante du config flow
    sur un message incompréhensible.
    """


class ConnectionError(PronoteAPIError):
    """Erreur de connexion réseau (DNS, timeout, unreachable)."""

    pass


class RateLimitError(PronoteAPIError):
    """API rate limit atteint (HTTP 429).

    Attributs:
        retry_after: Délai recommandé par l'API en secondes
    """

    def __init__(self, message: str, retry_after: int = 60) -> None:
        """Initialize avec retry_after par défaut de 60s."""
        super().__init__(message, retry_after=retry_after)


class IPSuspendedError(RateLimitError):
    """Pronote a suspendu l'adresse IP après trop de tentatives de connexion.

    C'est temporaire, et surtout ce n'est pas un problème d'identifiants :
    traité comme une panne d'authentification, cela déclenchait une demande de
    nouveau QR code, donc de nouvelles tentatives, donc une suspension plus
    longue. Hérite de RateLimitError pour que le coordinator réessaie plus tard
    au lieu d'ouvrir un reauth.
    """

    def __init__(self, message: str, retry_after: int = 900) -> None:
        """Initialize avec une attente par défaut de 15 minutes."""
        super().__init__(message, retry_after=retry_after)


class InvalidResponseError(PronoteAPIError):
    """Réponse API invalide (malformed JSON, unexpected format)."""

    pass


class SessionExpiredError(PronoteAPIError):
    """Session Pronote expirée, nécessite re-auth."""

    pass


class CircuitBreakerOpenError(PronoteAPIError):
    """Circuit breaker ouvert - trop d'échecs consécutifs."""

    pass
