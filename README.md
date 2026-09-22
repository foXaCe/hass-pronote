# Pronote integration for Home Assistant

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]
[![CI][ci-shield]][ci]
[![Maintenance][maintenance-shield]][maintenance]
[![Project Maintenance][maintainer-shield]][maintainer]

_Custom Home Assistant integration for Pronote (gestion de vie scolaire)._

## Features

- Connexion par identifiants ou QR code
- Capteurs : emploi du temps, notes, devoirs, absences, évaluations, moyennes, punitions, retards, menus
- Mise à jour automatique toutes les 15 minutes (par défaut)
- Diagnostics et repairs intégrés

## Installation

### Using HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=foXaCe&repository=hass-pronote&category=integration)

OR

If you can't find the integration, add this repository to HACS, then:
HACS > Integrations > **Pronote**

### Manual install

Copy the `pronote` folder from latest release to the `custom_components` folder in your `config` folder.

## Configuration

Click on the following button:
[![Open your Home Assistant instance and start setting up a new integration of a specific brand.](https://my.home-assistant.io/badges/brand.svg)](https://my.home-assistant.io/redirect/brand/?brand=pronote)

Or go to :
Settings > Devices & Sevices > Integrations > Add Integration, and search for "Pronote"

You can choose between two options when adding a config entry.

### Option 1: using username and password

Use your Pronote URL with username, password and ENT (optional):
![Pronote config flow](doc/config_flow_username_password.png)

### Option 2: using the QR Code

Create a QR Code from your Pronote account, then give the form its photo and the PIN you chose at generation. Those two fields are all it asks for.

A QR Code lasts ten minutes and works **once**: if a setup attempt fails, generate a new one rather than reusing it.

**Photo of the QR Code.** The upload field appears when a QR decoder is importable on your Home Assistant, that is both `pyzbar` (with the system `libzbar` library) and `Pillow`. Neither is declared as a requirement of this integration on purpose: a hard requirement for a decoder once made the whole config flow fail with a 500 on Home Assistant OS/Container. The picture is decoded locally; nothing is sent anywhere.

**Built-in QR Code reader.** When the photo cannot be read on the server — no decoder installed, or a blurry shot — the form links to a reader page served by the integration itself. It decodes the QR Code **in your browser** (the native `BarcodeDetector`, falling back to a bundled copy of [jsQR](https://github.com/cozmo/jsQR)), from a picture or from the camera, and gives you the JSON to paste back. Nothing leaves your browser, and no extension is needed.

Do not upload this credential-bearing QR Code to an online decoder.

The JSON it produces looks like:
```json
{"jeton":"XXXXXXXXXXX[...]XXXXXXXXXXXXXX","login":"YYYYYYYYYYYYYY","url":"https://[id of your school].index-education.net/pronote/..."}
```

![image](doc/config_flow_qr_code.png)

**Two-factor settings.** Pronote may re-run its mobile two-factor check days after the pairing, and answering it needs a device name and sometimes a PIN. Both have working defaults — the device is named `Home Assistant`, and the QR Code PIN doubles as the account PIN — so they are not asked at setup. If your Pronote mobile-app PIN differs from the QR Code one, set it in the integration options.

### Parent account

If using a Parent account, you'll have to select the child you want to add:
![image](doc/config_flow_parent.png)

## Usage

This integration provides several sensors, always prefixed with `pronote_LASTNAME_FIRSTNAME` (where `LASTNAME` and `FIRSTNAME` are replaced), for example `sensor.pronote_LASTNAME_FIRSTNAME_today_s_timetable`.


| Sensor                                    | Description                                 |
|-------------------------------------------|---------------------------------------------|
| `sensor.pronote_LASTNAME_FIRSTNAME_class` | basic informations about your child's class |
| `[...]_today_s_timetable`                 | today's timetable                           |
| `[...]_tomorrow_s_timetable`              | tomorrow's timetable                        |
| `[...]_next_day_s_timetable`              | next school day timetable                   |
| `[...]_period_s_timetable`                | timetable for next 15 days                  |
| `[...]_timetable_ical_url`                | iCal URL for the timetable (if available)   |
| `[...]_grades`                            | latest grades                               |
| `[...]_homework`                          | homework                                    |
| `[...]_period_s_homework`                 | homework for max 15 days                    |
| `[...]_absences`                          | absences                                    |
| `[...]_evaluations`                       | evaluations                                 |
| `[...]_averages`                          | averages                                    |
| `[...]_punishments`                       | punishments                                 |
| `[...]_delays`                            | delays                                      |
| `[...]_information_and_surveys`           | information_and_surveys                     |
| `[...]_menus`                             | menus (if available)                        |
| `[...]_overall_average`                   | overall average                             |

The sensors are updated every 15 minutes.

## Removal

To remove the integration:
1. Go to Settings > Devices & Services > Integrations
2. Find the Pronote integration entry you want to remove
3. Click the three dots menu (⋮) and select "Delete"
4. Restart Home Assistant

To fully uninstall, also remove the `pronote` folder from `custom_components` and remove it from HACS.

## Cards

Cards are available here: https://github.com/delphiki/lovelace-pronote

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)

<!-- Badges links -->
[releases-shield]: https://img.shields.io/github/release/foXaCe/hass-pronote.svg?style=for-the-badge
[releases]: https://github.com/foXaCe/hass-pronote/releases
[license-shield]: https://img.shields.io/github/license/foXaCe/hass-pronote.svg?style=for-the-badge
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[ci-shield]: https://img.shields.io/github/actions/workflow/status/foXaCe/hass-pronote/ci.yml?branch=main&style=for-the-badge
[ci]: https://github.com/foXaCe/hass-pronote/actions/workflows/ci.yml
[maintenance-shield]: https://img.shields.io/maintenance/yes/2026.svg?style=for-the-badge
[maintenance]: #
[maintainer-shield]: https://img.shields.io/badge/maintainer-%40foXaCe-blue.svg?style=for-the-badge
[maintainer]: https://github.com/foXaCe
