# Built-in Skills

This document enumerates the built-in skills, their purpose, matching patterns, side-effect stores, and the execution order.

- **Order**: The skills are listed in `app/skills/__init__.py` in a deterministic order. This order is preserved to make matching predictable and testable.

- **Side-effect stores**: Notes are persisted to `notes.db`, reminders to `data/reminders.json`, timers to `data/timers.json`. Many device-control skills call Home Assistant via `app.home_assistant` directly.

Skills (one-line summaries):

- `SmalltalkSkill`: greeting detection; returns canned greetings. Matches via custom `is_greeting()` logic.
- `ClockSkill`: report time/date; regex-based patterns.
- `WorldClockSkill`: show time in cities; regex patterns.
- `WeatherSkill`: fetches current weather; patterns like "weather in <city>"; calls OpenWeather API.
- `ForecastSkill`: 3-day forecast; regex patterns + OpenWeather.
- `ReminderSkill`: schedule reminders; patterns for "remind me" variants; persists to `data/reminders.json` and uses `apscheduler` if available.
- `TimerSkill`: start/pause/resume/cancel timers; persists to `data/timers.json` and interacts with HA `timer` service.
- `MathSkill`: arithmetic and percentages; regex patterns and safe evaluation.
- `UnitConversionSkill`: converts units (C↔F, km↔mi); regex patterns.
- `CurrencySkill`: currency conversion; regex patterns and external API calls.
- `CalendarSkill`: show calendar events; regex patterns.
- `TeachSkill`: alias mapping ("my bedroom is X"); patterns for aliasing; writes to `alias_store`.
- `EntitiesSkill`: list Home Assistant entities; read-only via HA states.
- `SceneSkill`: activate Home Assistant scenes; patterns like "activate <name> scene".
- `ScriptSkill`: run predefined scripts/aliases; regex patterns and HA calls.
- `CoverSkill`: open/close covers; HA calls.
- `FanSkill`: turn fans/air purifiers on/off; HA calls.
- `NotifySkill`: send notifications; HA or external notifier.
- `SearchSkill`: DuckDuckGo instant answers; regex patterns starting with "search".
- `TranslateSkill`: translate/detect language via `TRANSLATE_URL` service.
- `NewsSkill`: fetch headlines; regex patterns.
- `JokeSkill`: fetch a random joke; regex patterns.
- `DictionarySkill`: define words; regex patterns.
- `RecipeSkill`: fetch recipe steps/ingredients; regex patterns.
- `LightsSkill`: control lights and brightness; patterns for on/off and brightness; resolves friendly names and calls HA `light` service.
- `DoorLockSkill`: lock/unlock doors; HA calls.
- `MusicSkill`: play/pause/artist; patterns for media control; calls HA media_player services; uses `artist_map.json`.
- `RokuSkill`: launch Roku apps; HA or provider calls.
- `ClimateSkill`: thermostat controls; HA calls.
- `VacuumSkill`: start/stop vacuum; HA calls.
- `NotesSkill`: add/list/show/delete notes; persists to `notes.db` (SQLite).
- `StatusSkill`: report backend, HA, and LLaMA health; read-only queries.

For full details refer to each skill implementation in `app/skills/`.
