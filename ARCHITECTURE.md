# Architecture

L'intégration Pronote suit le pattern standard Home Assistant : un
`DataUpdateCoordinator` (polling 15 min) alimente les entités (capteurs,
calendrier) à partir du client API pronotepy.

## Flux

```
ConfigFlow (identifiants / QR code)
   │
   ▼
Client API Pronote (custom_components/pronote/api/)
   │  authentification (identifiants / ENT / QR code + PIN)
   ▼
DataUpdateCoordinator (coordinator.py) — polling 15 min
   │  fetch_all_data()
   ▼
Entities : sensor.py (emploi du temps, notes, devoirs, ...),
           calendar.py (devoirs)
Diagnostics : diagnostics.py
Repairs : repairs.py (reauth quand la session expire)
```

## Modules

| Fichier | Rôle |
|---------|------|
| `__init__.py` | setup de l'intégration, montage du coordinator |
| `config_flow.py` | configuration utilisateur (2 options : identifiants / QR code) |
| `coordinator.py` | DataUpdateCoordinator, polling, détection de changement |
| `api/` | client Pronote : auth, circuit breaker, modèles, exceptions |
| `sensor.py` | entités capteurs |
| `calendar.py` | entité calendrier (devoirs) |
| `diagnostics.py` | export de diagnostic |
| `repairs.py` | issues de réparation (session expirée) |
| `_compat.py` | patch compatibilité pronotepy / Python 3.13+ |

## Robustesse

- Circuit breaker sur l'API (`api/circuit_breaker.py`)
- Rotation des jetons détectée et persistée (fix silent token rotation)
- Reauth automatique proposé quand la session expire
