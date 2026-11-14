# Morsoul cloud backend

The cloud half of the game client: accounts, per-profile cloud saves, update manifest, global statistics and a small admin review. Python, FastAPI, MongoDB (async PyMongo).

It follows `kiro-game-client-brief.md` (sections 8 to 10) and the snapshot contract in `game-backend-spec.md` (section 8). The launcher and the game service are separate projects that talk to this one.

## What is in here

```
morsoul_core/      shared with the launcher: snapshot model, hash + HMAC, validation rules, content loader, update manifest signing
morsoul_server/    the FastAPI app (routes, middleware, rate limiter, sessions, errors)
scripts/           gen_keys, build_manifest, sign_manifest, make_admin, write_server_json
tests/             59 tests (in-memory Mongo by default, real MongoDB with TEST_MONGO_URI)
```

## Quick start

```bash
uv sync                                    # installs everything, including the dev tools
cp .env.example .env                       # then edit it
uv run python scripts/gen_keys.py --private-key keys/update-signing.pem
#   paste SAVE_HMAC_KEY (and UPDATE_PUBLIC_KEY) into .env; keep keys/ out of git

# MongoDB must be running on 127.0.0.1 (bind it to localhost only, never to Wi-Fi)
uv run python -m morsoul_server            # serves http://127.0.0.1:8080
```

Check it: `curl http://127.0.0.1:8080/api/v1/health` returns `{"status":"ok"}`.
Set `API_DEBUG=true` only while developing to get the interactive docs at `/docs`.

### Expose it with a Cloudflare Tunnel

```bash
cloudflared tunnel --url http://localhost:8080
uv run python scripts/write_server_json.py https://<the-address-it-prints>.trycloudflare.com
# commit server.json to the repo your launcher's SERVER_CONFIG_URL points to
```

* A quick tunnel gets a new address on every start, so repeat the last two steps each time.
* Do not use the tunnel's email-PIN option (the launcher cannot enter it) and do not use Server-Sent Events.
* Keep `TRUST_CF_HEADER=true` only because the server listens on 127.0.0.1 and is reachable only through the tunnel. Otherwise anyone could fake the client IP used for rate limits.

### Make an admin

Register normally in the launcher, then: `uv run python scripts/make_admin.py <username>`.

### Publish an update

```bash
uv run python scripts/build_manifest.py --dir build/ --base-url https://github.com/<you>/<repo>/releases/download/v1.0.0 --app-version 1.0.0 --content-version 1
uv run python scripts/sign_manifest.py --key keys/update-signing.pem
# copy updates/manifest.json and updates/manifest.sig into the server's UPDATES_DIR
```

The server only serves these two files. If `UPDATE_PUBLIC_KEY` is set it also refuses to serve a manifest that fails verification (a safety net against a bad publish). The private key never goes on the server.

### Back up

`mongodump --db morsoul --out backups/$(date +%F)` regularly, to a place that is not this laptop, and test one restore (`mongorestore`) before the demo.

## Tests

```bash
uv run pytest                                          # in-memory Mongo stand-in, runs anywhere
TEST_MONGO_URI=mongodb://127.0.0.1:27017 uv run pytest # the same tests on a real MongoDB (temporary databases)
uv run ruff check . && uv run mypy morsoul_core morsoul_server
```

Run the suite against real MongoDB at least once. The two "simultaneous uploads" tests only prove the atomic update when the database does the atomic work.

## API (`/api/v1`)

All errors look like `{"error": {"code", "message", "details"?}}`.

| Method and path | Session | Notes |
|---|---|---|
| POST `/auth/register`, `/auth/login` | no | `{userID, username, sessionToken, expiresAt}`. 409 `USERNAME_TAKEN` / `EMAIL_TAKEN`, 401 `INVALID_CREDENTIALS` |
| POST `/auth/logout`, `/auth/logout-all`; GET `/auth/me` | yes | 204 on logout |
| POST `/auth/change-password` | yes | `{currentPassword, newPassword}`; 403 `WRONG_PASSWORD`; deletes every session, returns a fresh one for this device |
| DELETE `/auth/account` | yes | body `{password}`; removes the user, sessions, saves and history |
| GET `/saves` | yes | the account's profiles with `{revision, stateHash, summary}` |
| GET `/saves/{profileId}/latest` | yes | `{revision, snapshot}` |
| PUT `/saves/{profileId}` | yes | `{baseRevision, snapshot}`. 200 `{revision, summary}`, 409 `REVISION_CONFLICT` (details: `serverRevision`, `stateHash`, `summary`), 403 `FORBIDDEN_PROFILE`, 404, 413, 422 `INVALID_SAVE` (details: `issues`) |
| GET `/saves/{profileId}/history`, `/history/{revision}` | yes | newest 5 versions |
| DELETE `/saves/{profileId}` | yes | removes the cloud copy and its history |
| GET `/stats` | yes | per case: players and the share of each conclusion (flagged saves excluded, no usernames) |
| GET `/updates/manifest` | no | `{manifest, signature}` or 404 |
| GET `/health` | no | `{status}` only |
| GET `/admin/flagged-saves`; POST `/admin/saves/{profileId}/unflag` | admin | |

Limits (per minute): 120 per IP overall, 10 per IP for login and register, 5 per user for change-password, 60 per user for save routes, 30 per IP for updates. Request bodies over 512 KB get 413.

## The snapshot contract (what the launcher must send)

The server stores and validates the snapshot exactly as the sender produced it. The model is `morsoul_core/snapshot.py`; unknown fields are rejected.

* Envelope: `profileID, schemaVersion, contentVersion, appVersion, revisionID, updatedAt, playtime, stateHash, signature, payload`.
* `stateHash` = SHA-256 of the canonical JSON of `payload`. `signature` = HMAC-SHA256 over the canonical JSON of the whole envelope **without** the `signature` field. Both use `morsoul_core.integrity` (`seal(snapshot, key)` fills them in), where canonical JSON means sorted keys, compact separators, UTF-8. The launcher must use the same functions, otherwise every upload is rejected with 422.
* Round floats to 3 decimals before sealing so export, import, export gives byte-identical snapshots.
* All keys must be plain identifiers (`A-Z a-z 0-9 _ -`, up to 64 characters). Keys such as `$where` or `a.b` are rejected, and nesting deeper than 8 levels is rejected.
* `baseRevision` is the cloud revision the launcher last synced with (0 for the first upload). It is not the local `revisionID`.

## What the server checks on an upload

Shape, keys, hash, signature, profile ID equals the URL, then the rules in `morsoul_core/validation.py`: at most four Runic Logs, ending consistent with the logs, links, pins and notes only use found clues, results only for completed cases, focus time not after playtime, and (when `CONTENT_DIR` points at the game files) every ID exists and tools unlocked by a case need that case completed. It does **not** require progress to only grow, because "keep local" after a conflict may legitimately replace newer cloud progress; the last 5 versions are kept instead.

Implausible saves (for example three completed cases in a minute) are stored, flagged for an admin, left out of the statistics, and the client is not told. The thresholds are `MIN_SECONDS_PER_COMPLETED_CASE` and `MIN_SECONDS_PER_CLUE`; they are placeholders to tune.

## Differences from the written spec (on purpose)

* One project with two packages instead of a uv workspace with separate apps.
* A 40-line in-memory rate limiter instead of `slowapi`, because per-user limits need the session.
* No separate `profiles` collection: `saves` documents carry `user_id` (ownership) and the display name. The first uploader claims a profile ID.
* Validation failures are 422 `VALIDATION_ERROR` (the brief said 400).
* The save summary has no `rank`; the launcher computes it from `reputation` and `ranks.json`.
* The optional `LAUNCHER_KEY` header from the prototype is kept as a noise filter. It lives inside the launcher, so it is not authentication.

## Not built yet

* The launcher itself (`launcher_core`: sync engine, updater, token store) and the game service.
* Rank thresholds, interrogation and hint rules: they belong to the game logic, not the cloud.
* Per-IP limits behind a second proxy, and distributed rate limiting (one process is assumed).
