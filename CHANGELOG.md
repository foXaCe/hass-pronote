# Changelog

## [1.1.1] - 2026-02-13

### Fixed

- menu sensor not loading due to incomplete data model conversion (missing meal categories and food labels)
- format_food_list crash when food labels are None
- UpdateFailed retry_after keyword not supported in current HA version

### Maintenance

- align all test fixtures with data model attributes (room, teacher, grade_out_of, etc.)
- fix calendar test timezone-aware datetime comparison

## [1.1.0] - 2026-02-12

### Added

- configurable grades limit per entity (1-50) via options flow
- show all periods option for future period entities (per semester/trimester)
- compact timetable format for period sensor (fixes 16KB attribute limit)
- repairs support for session expiration, rate limiting and connection errors
- MIT LICENSE file

### Changed

- Platinum-level API client with resilience patterns (retry, circuit breaker, rate limiting)
- session reuse optimization (skip re-authentication when connected)
- previous period data cache (past trimesters cached daily)
- async authentication for proper executor handling
- overall average normalization (French comma to float)
- refresh time reduced from ~2.5s to ~1.2s

### Fixed

- calendar naive/aware datetime comparison error
- missing translation keys for repair issues
- missing option keys in Portuguese translations
- repair flow translation key handling

### Maintenance

- update tests for refactored API and config flow
- fix ruff formatting and lint errors

## [1.0.0] - 2026-02-10

### Added

- add event new_evaluation if new evaluation is detected
- add overall averages sensors
- change sensors naming and grouping
- handle period related sensors
- retrieve periods related data
- add periods and current period sensors
- rename sensors to be more readable
- add nickname step with default value based on child name
- add calendar sensor
- add limit for info and surveys sensor
- add configurable next alarm sensor
- add options system
- add event triggering on new grade, delay and absence
- use config entry instead of file for storing token
- handle config entry migration from v1 to v2
- add day_end_at attribute
- add sensor for menus
- add sensor for student's timetable iCal url
- add todo counter and fix typo in attribute name
- add canceled lessons counter
- add english and french translations
- add basic HACS config

### Changed

- rewrite integration for HA platinum quality scale
- add global errors catching on period related methods
- use local variable to reduce memory print
- code optimizations and clean up
- code improvements
- handle login in a specific file + code clean up
- add coordinator to handle updates

### Fixed

- resolve pip dependency conflicts
- align ruff version and resolve dependency conflict
- use datetime instead of date to retrieve info and surveys
- update condition causing an exception to be thrown for lessons_nextday data
- update to pronotepy 2.14.5 to fix the auth issues
- bump pronotepy version to 2.14.4 to include latest fixes
- add back error catching on info and surveys
- add missing zip_release key in hacs.json
- add missing attributes on all sensors
- update check for sensors states
- update to pronotepy@2.14.2 to handle latest breaking Pronote update
- use hotfix from @bain3 for python 3.13
- temp use of pronotepy fork to support python 3.13
- fix condition to check if tomorrow is a school day
- add missing device class for next_alarm sensor
- change state to 0 instead of unavailable
- remove class_average for comparison
- properly handle next alarm
- extend from TimestampDataUpdateCoordinator
- allow empty nickname
- properly convert schedule duration to string
- update only the coordinator instead of reloading the entry
- use proper value for day start
- properly init user inputs attribute
- better sensor state handling
- limit search for upcoming lessons
- remove useless ids in evaluation sensor
- add missing account_type data for user/pwd login
- use spaces instead of tabs for indentation on PronotePunishmentsSensor
- properly handle day_start_at value for lessons
- prevent sensor crash if coordinator data corrupted
- better handling of sensor attributes
- add try/except on all api calls
- fix delays
- mark ical and menus sensors as unavailable is error
- bump version to 0.6.1
- temp remove of ical url sensor
- typo on homework
- restore update interval to 15 minutes
- properly handle client return values
- sorted keys in manifest.json
- add missing issue_tracker in manifest.json
- user proper value for timetable state update
- add missing version number in manifest

### Maintenance

- rewrite release workflow with auto changelog from conventional commits
- fix ruff format on test files for pre-commit compliance
- fix ruff format on calendar, config_flow, coordinator
- add gitignore and update readme
- achieve 99.69% coverage with 298 tests
- bump pytest from 8.3.4 to 9.0.2
- bump pytest-cov from 6.0.0 to 7.0.0
- bump pytest-homeassistant-custom-component
- bump pytest-asyncio from 0.25.3 to 1.3.0
- bump actions/upload-artifact from 4 to 6
- bump actions/checkout from 4 to 6
- add comprehensive test suite for all modules
- bump actions/setup-python from 5 to 6
- bump actions/stale from 9 to 10
- bump softprops/action-gh-release from 2.2.1 to 2.5.0
- fix linting and formatting across codebase
- add test infrastructure and dev tooling
- add complete CI/CD pipeline and GitHub templates
- add missing content permission
- use zip releases for HACS
- replace pytz with ZoneInfo
- code clean up and reformating using black
- bump pronotepy version to 2.14.1
- bump pronotepy version to 2.13.1
- update pronotepy version
- bump manifest version
- refactor sensors to prevent code duplication
- bump version to 0.6.0
- bump pronotepy version to 2.12.1
- bump pronotepy to 2.12.0
- add actions for hassfest and HACS
