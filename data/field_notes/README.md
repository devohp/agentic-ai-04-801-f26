# Field-note corpus (Challenge B)

Synthetic notes written in the style of extension officers: telegraphic, English mixed with Kiswahili,
abbreviations, phonetic spellings, missing units, blank form fields. A small share is written in Kinyarwanda;
those notes were checked by a native speaker. **No real farmer, officer or field
is described.** The notes refer to the fields in `../fields.csv` and can be cross-checked against
`../weather_daily.csv`, `../ndvi_monthly.csv` and `../field_seasons.csv`.

## Files

| File | Content |
|---|---|
| `field_notes.jsonl` | One note per line: `note_id`, `recorded_on` (ISO date the note was written), `officer_id`, `format` (`free_text` or `form`), `text` |
| `dev_gold.jsonl` | Gold events for the development split (about one note in five). The remaining notes are the test split; their gold stays with the teaching team |

## Gold schema (`dev_gold.jsonl`)

Each note has a list of `events`. Each event has:

| Key | Meaning |
|---|---|
| `what` | one code from the vocabulary below |
| `where` | canonical `field_id`, or `null` if the note names a field that cannot be resolved |
| `when` | ISO date of the event (resolve `leo` = today, `jana` = yesterday, `juzi` = day before yesterday relative to `recorded_on`; a date written in the note wins) |
| `severity` | `low`, `medium`, `high` or `unspecified`, as stated by the officer; never inferred from other data |
| `data_check` | `corroborated`, `contradicted`, `inconclusive` or `not_checkable` (rules below) |

## Vocabulary for `what`

- `pest_fall_armyworm`: fall armyworm (Spodoptera frugiperda), stated or clearly described
- `pest_armyworm_unresolved`: an armyworm or caterpillar report whose species cannot be resolved from the note
- `pest_stalk_borer`: stalk borer suspected
- `pest_unidentified`: insect or pest damage reported, organism not named
- `disease_msv_suspected`: maize streak virus suspected
- `leaf_yellowing`: yellowing leaves, cause not established
- `nutrient_n_deficiency_suspected`: officer explicitly suspects nitrogen deficiency
- `drought_stress`: drought or water stress reported
- `waterlogging`: standing water or waterlogging reported
- `washout`: seedlings washed out or soil eroded by rain
- `weed_pressure`: weeds reported
- `input_fertilizer`: fertilizer applied
- `input_pesticide`: pesticide or botanical applied
- `planting`: planting done
- `poor_emergence`: poor or uneven emergence
- `harvest`: harvest done or under way
- `advice_requested`: the farmer asks for a product or advice (a question, not an action taken)

## Rules behind `data_check`

| Event | corroborated | contradicted |
|---|---|---|
| `drought_stress` | at least 10 of the 14 days before the event had less than 1 mm rain (`weather_daily.csv`, site of the field) | the 7 days before the event had 50 mm or more |
| `waterlogging`, `washout` | a day with 30 mm or more in the 3 days before, or 80 mm or more in the 7 days before | less than 5 mm in the 7 days before |
| `input_fertilizer` | `use_inorg_fert` is 1 for that field and season in `field_seasons.csv` | `use_inorg_fert` is 0 |
| `planting` | within 7 days of `planting_date` in `field_seasons.csv` | more than 7 days away |

Everything else is `not_checkable` from the data in this repository. Values of -999 in the weather file count as missing.

## Severity words you will meet

`kidogo` (a little), `wachache` (few), `chini` (low), `kiasi` (moderate), `wastani` (average), `robo ya mimea` (a quarter of the
plants), `nusu ya shamba` (half the field), `wengi sana` (very many), `mkali` (severe); in Kinyarwanda
`byinshi` (many). The gold keeps the
officer's level; it does not convert words into percentages.
