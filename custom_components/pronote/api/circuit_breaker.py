"""Circuit breaker pattern for API resilience."""

from __future__ import annotations

import logging
from datetime import datetime

_LOGGER = logging.getLogger(__name__)

# Configuration par défaut
DEFAULT_FAILURE_THRESHOLD = 5
DEFAULT_RECOVERY_TIMEOUT = 300  # 5 minutes


class CircuitBreaker:
    """Circuit breaker pour protéger contre les cascades d'erreurs.

    Le circuit breaker passe par 3 états:
    - CLOSED: Fonctionnement normal, les appels passent
    - OPEN: Trop d'échecs, les appels sont rejetés immédiatement
    - HALF-OPEN: Après timeout, une tentative est autorisée
    """

    def __init__(
        self,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        recovery_timeout: int = DEFAULT_RECOVERY_TIMEOUT,
    ) -> None:
        """Initialize le circuit breaker.

        Args:
            failure_threshold: Nombre d'échecs avant ouverture
            recovery_timeout: Temps avant tentative de fermeture (secondes)
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time: datetime | None = None
        self._is_open = False

    @property
    def is_open(self) -> bool:
        """Vérifie si le circuit est ouvert (bloquant).

        Returns:
            True si le circuit est ouvert et le timeout non écoulé
        """
        if not self._is_open:
            return False

        # Vérifier si on peut tenter de fermer
        if self._last_failure_time:
            elapsed = (datetime.now() - self._last_failure_time).total_seconds()
            if elapsed >= self.recovery_timeout:
                _LOGGER.debug("Circuit breaker: tentative de fermeture après timeout")
                self._is_open = False
                self._failure_count = 0
                return False

        return True

    def record_success(self) -> None:
        """Enregistre un succès - réinitialise le compteur."""
        if self._failure_count > 0:
            _LOGGER.debug("Circuit breaker: succès, réinitialisation")
        self._failure_count = 0
        self._is_open = False

    def record_failure(self) -> None:
        """Enregistre un échec - incrémente le compteur.

        Si le nombre d'échecs atteint le threshold, le circuit s'ouvre.
        """
        self._failure_count += 1
        self._last_failure_time = datetime.now()

        if self._failure_count >= self.failure_threshold:
            _LOGGER.warning(
                "Circuit breaker OUVERT après %s échecs consécutifs",
                self._failure_count,
            )
            self._is_open = True

    def reset(self) -> None:
        """Réinitialise manuellement le circuit breaker."""
        self._failure_count = 0
        self._last_failure_time = None
        self._is_open = False
        _LOGGER.debug("Circuit breaker: réinitialisation manuelle")
