# Aangan runbook (English mode)

## Start everything

1. Backend (port 8000): `cd backend && uv run uvicorn app.main:app --port 8000`
2. Frontend (port 5190): `cd frontend && npm run dev -- --port 5190 --strictPort`
3. Tunnel, so Agora's cloud can call the backend: `tools\cloudflared.exe tunnel --url http://localhost:8000 --no-autoupdate`
   It prints `https://<words>.trycloudflare.com`. The address is new every time the tunnel restarts.
4. Record the address: `cd backend && uv run python ../scripts/set_tunnel.py https://<words>.trycloudflare.com`, then restart the backend so it reads it.

Open http://localhost:5190 on the same computer (microphone access needs localhost or HTTPS).

## First run

The app starts empty. On first open it shows Welcome:
1. **Set up my family**: your profile (name, role, age, the voice Aangan uses with you), then the people in your family (name, relation, age, optional allergies and diet), then Start. Or press **Try the demo family** for an example household (Priya, Rahul, Aarav and Dadi with a week of events and spending), which Settings, Household can reset.
2. The browser remembers who you are. Another device or browser that opens the app sees "Who's using Aangan?" and picks a person, or adds themselves. Switch profile any time in Settings.
3. The family is saved on the backend (`backend/data/household.json`, git-ignored), so it survives restarts. Settings, Household, Reset household empties it.

## The four tabs

Home (what needs attention, what Aangan has done for you, spending), **Ask** (talk or type to Aangan; "What Aangan did" shows every action in plain sentences), Family (People, Schedule, Spending), Settings.

## Live voice test (English)

1. Ask tab, press **Talk to Aangan**, allow the microphone.
2. Wait for "Hello <your name>, Aangan here. What can I do for the family today?"
3. Say one thing, then wait for the reply:
   - "Let's all go out for lunch on Sunday", then "Yes, book it". Check Family, Schedule.
   - "When is everyone free on Sunday?"
   - "I spent 450 on groceries", "How much did we spend this month?", "How can we save money?"
   - "Remember that I like spicy food."
   - With a child or grandparent in the family: "How is <child> doing in school?", "Did <grandparent> take her medicines today?"
4. Press **End** when done. The agent also exits by itself after 30 seconds without a caller.

## If something fails

| Symptom | Check |
|---|---|
| Voice button disabled, "not connected" | Settings lists the missing `.env` keys |
| 409 "Set up your family first" | The household is empty: finish setup |
| Agent joins but never answers | Tunnel down or address changed: open `<tunnel>/v1/chat/completions` (expects 401/405, not 530), rerun step 4 |
| Cloudflare error 530 | The tunnel process stopped: restart it and rerun step 4 |
| No transcripts, voice works | RTM: check Connection details in the voice panel |
| Wrong or no answer to a phrase | Ask, What Aangan did: see which agent handled it |
| App shows an old version | A cached service worker: press Update on the banner, or clear site data |

## Switching to other languages later

Set `AANGAN_LANGUAGE_MODE=native` in `backend/.env` and restart the backend: members then hear and speak their own language. Test Hinglish recognition first, since it depends on Deepgram's romanised Hindi mode.
