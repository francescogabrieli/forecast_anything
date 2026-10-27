# Console observed usability study

Status: **on hold by owner decision on 2026-10-27; sessions not yet run**. Development and technical-preview preparation continue without waiting for recruitment. Do not report usability acceptance until five external participants complete the study and results are recorded. Resume this protocol when participants are available; the acceptance criterion is unchanged.

## Goal

Find whether a new user can connect and activate a supported CSV source, then understand a recorded discovery and its evidence without maintainer instruction. This measures the source-connection and observatory path; it does not measure forecast quality or natural-language forecast authoring.

## Participants and privacy

- Recruit five people who are not maintainers and have not used Forecast Anything before. Prefer a mix of data familiarity and technical comfort; record only broad categories, not employer or personal data.
- Assign IDs `P1`–`P5`. Do not collect names in the results file.
- Use synthetic CSV data and a local workspace. Do not record screens or audio by default. Ask separately before any recording, and allow a participant to decline without stopping the session.
- Tell participants that the product is being tested, not their ability. They may stop at any time.

## Setup

- Use a clean workspace for each participant, the normal console build, and a fixed clock and synthetic fixture so every person sees the same discovery and evidence. The values are deterministic and the dates are generated for the session, so the forecast target remains in the future.
- Give each participant the local console URL, workspace token, source ID, and the `Usability CSV:` path printed by the API terminal (Compose uses `/data/...`). The API clock is frozen when the server starts; restart it between participants. Do not explain the column mapping or where the discovery appears.
- Confirm before the session that the source profile is unresolved, activation produces the expected deterministic discovery, and the discovery has a recorded run/evidence view. Reset the workspace after each participant.
- Keep provider calls disabled. This study tests navigation and interpretation using local deterministic evidence.

For the current deterministic fixture, use two local terminals from the repository root:

```sh
FA_USABILITY=1 FA_USABILITY_PORT=8010 uv run --locked --extra dev python tests/e2e/serve_observatory.py
npm --prefix apps/console run dev -- --host 127.0.0.1 --port 4173
```

The fixture API binds to loopback, seeds synthetic sources, a run, evaluation and watches, writes a current-dated synthetic CSV, then starts its worker. Give participants the API URL and CSV path printed by the API terminal, plus the test-only token `local-e2e-token` and source ID `study-sales`. Set the console’s API address to the printed URL. Keep the server on loopback and never use real data. Restart the API process between participants to reset state and generate a fresh path. If the study uses a containerized setup instead, prepare a fresh workspace and unique local token for every participant.

## Moderator introduction

> We are testing this software, not you. Please say what you are looking for and what you expect as you work. I will avoid helping unless you ask to stop. You can stop at any time. The data is synthetic and local.

Do not explain interface labels, data semantics, or the intended discovery. If asked for help, say: “What would you try if I weren’t here?” Record the request. After the task timeout, help the participant finish, but count that task as requiring assistance.

## Tasks

1. **Connect and activate:** “This CSV contains a time series. Connect it so the workspace can use it. Review the interpretation and activate it when you think it is ready.”
2. **Understand a discovery:** “Find the latest discovery. Explain what it is about, what evidence supports it, and whether you would act on it now or investigate further.”

Allow five minutes per task. A neutral reminder to think aloud is not assistance. Any instruction that reveals a field mapping, navigation target, or interpretation is assistance and must be recorded.

## Scoring

The preregistered acceptance criterion from the roadmap is **at least four of five participants complete both tasks without maintainer instruction**.

For task 1, completion means the source is active and required fields are interpreted correctly: event time, value, availability, series identity, unit, frequency, timezone, calendar, revision, and missing-value marker. A participant may use the preview and correct their mapping without it counting as assistance.

For task 2, completion means the participant can identify the discovery's subject and source, point to the displayed evidence/run, explain its current quality or lifecycle in plain language, and distinguish a supported observation from an assumption. Do not require the participant to endorse a particular action.

For each task, record completion, elapsed time, whether help was requested, the first point of confusion, and any blocking error. Capture notable interface text verbatim without personal data. After the tasks, ask:

- “What did you think the system was doing when you got stuck?”
- “What evidence would you want before acting on this discovery?”
- “What is the one change that would make this easier?”

## Result sheet

Copy this row once per participant and fill it during the session:

| ID | Data familiarity | Technical comfort | Connect complete unaided? | Connect time | Discovery understood unaided? | Discovery time | Help/blockers | Most useful change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1 |  |  |  |  |  |  |  |  |

After all five sessions, report the numerator for the 4/5 criterion, task completion and help counts, recurring blockers, and specific changes to make. Preserve failed attempts and dissenting feedback; do not exclude a session because the participant struggled.
