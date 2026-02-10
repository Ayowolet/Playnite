# Platform API Setup Guide

## Steam

1. **Obtain a Steam API Key**
   - Visit <https://steamcommunity.com/dev/apikey>
   - Sign in with your Steam account
   - Enter any domain name (e.g. `localhost`) and accept the terms
   - Copy the generated key

2. **Find your Steam ID**
   - Visit your Steam profile page
   - The 17-digit number in the URL is your SteamID64 (e.g. `76561198000000001`)
   - Alternative: visit <https://steamid.io> and enter your vanity URL

3. **Configure**
   ```bash
   playnite config set steam.api_key YOUR_KEY_HERE
   playnite config set steam.steam_id 76561198000000001
   playnite config set steam.enabled true
   ```
   Or set environment variables:
   ```bash
   export STEAM_API_KEY=YOUR_KEY_HERE
   export STEAM_ID=76561198000000001
   ```

4. **Test**
   ```bash
   playnite achievements sync --platform steam
   ```

---

## Xbox Live (via OpenXBL)

1. **Register at OpenXBL**
   - Visit <https://xapi.us> and create a free account
   - The free tier allows 200 requests per hour (sufficient for personal use)
   - Copy your API key from the dashboard

2. **Find your XUID**
   - Sign in at <https://www.xbox.com/en-US/play>
   - Your XUID is the numeric identifier in profile URLs
   - Alternative: use <https://xboxgamertag.com> to look up by gamertag

3. **Configure**
   ```bash
   playnite config set xbox.api_key YOUR_OPENXBL_KEY
   playnite config set xbox.xuid YOUR_XUID
   playnite config set xbox.enabled true
   ```

4. **Test**
   ```bash
   playnite achievements sync --platform xbox
   ```

---

## PlayStation Network (PSN)

PSN uses an NPSSO token for authentication. This token is obtained from the
PlayStation website session cookie.

1. **Obtain your NPSSO token**
   - Open a browser and sign in at <https://www.playstation.com>
   - Navigate to: <https://ca.account.sony.com/api/v1/ssocookie>
   - You will see JSON containing `"npsso": "TOKEN_VALUE"`
   - Copy the token value (valid for approximately 60 days)

2. **Configure**
   ```bash
   playnite config set psn.npsso_token YOUR_NPSSO_TOKEN
   playnite config set psn.enabled true
   ```
   Or:
   ```bash
   export PSN_NPSSO=YOUR_NPSSO_TOKEN
   ```

3. **Test**
   ```bash
   playnite achievements sync --platform psn
   ```

> **Note**: The NPSSO token expires. When syncing fails with a 401 error,
> repeat step 1 to refresh the token.

---

## GOG Galaxy

GOG uses OAuth 2.0. The authentication flow requires interactive browser login.

1. **Obtain OAuth credentials**
   - GOG does not publicly distribute OAuth client credentials; the integration
     uses the embedded GOG credentials from the Galaxy client.
   - For personal use, set `access_token` and `refresh_token` directly after a
     GOG Galaxy client login session (tokens are stored in the Galaxy client's
     local database).

2. **Configure via token (recommended)**
   ```bash
   playnite config set gog.access_token YOUR_ACCESS_TOKEN
   playnite config set gog.refresh_token YOUR_REFRESH_TOKEN
   playnite config set gog.enabled true
   ```

3. **Test**
   ```bash
   playnite achievements sync --platform gog
   ```

> **Note**: GOG tokens have a short lifetime. The adapter automatically
> refreshes them using the stored `refresh_token`.

---

## Manual Entry (no API required)

For platforms without API support (Nintendo, older consoles, DRM-free games):

```bash
# Add a game
playnite achievements add-manual --game "My Retro Game" --name "First Stage Clear" --unlocked

# Add with a specific unlock date
playnite achievements add-manual \
  --game "My Retro Game" \
  --name "All Bosses" \
  --unlocked \
  --unlock-date 2024-03-15

# Add a progress-based achievement
playnite achievements add-manual \
  --game "My Retro Game" \
  --name "Collector" \
  --description "Collect 100 items" \
  --max-value 100 \
  --current-value 42
```

---

## Syncing All Platforms

```bash
# Sync all configured platforms
playnite achievements sync

# Force re-sync (ignores recent sync cache)
playnite achievements sync --force

# JSON output for scripting
playnite achievements sync --json
```

## Automatic Sync

Configure automatic sync via a backup profile schedule or via cron:

```bash
# Add to crontab (sync every 6 hours)
0 */6 * * * /usr/local/bin/playnite achievements sync >> ~/.playnite/sync.log 2>&1
```
