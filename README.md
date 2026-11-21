# Aangan

A family voice assistant. One shared memory of everyone in the family, and a team of specialist agents that act for them: travel, calendar, dining, school, senior care and household memory. Built for the Build with Agora Bengaluru 2026 hackathon (PS21, Agentic Workflow Opportunity).

Each family member talks to Aangan in their own language and voice. Aangan remembers allergies, diets, access needs, budgets and routines, checks everyone's calendars, books things, and tells the right people.

## Run

Backend (needs [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
uv sync
uv run uvicorn app.main:app --port 8000
```

Frontend (Vite PWA):

```bash
cd frontend
npm install
npm run dev
```

Tests: `cd backend && uv run pytest`.

## Architecture

```
PWA (Vite + React, AI Elements)  --RTC audio-->  Agora Conversational AI Engine
        |                                          |  ASR (Agora) -> our LLM endpoint -> Murf Falcon TTS
        | REST                                     v
        +-------------> FastAPI backend <---- POST /v1/chat/completions?member=<id>
                          orchestrator -> specialist agents -> tools
                          shared family state (members, memory, calendar, per-agent domains)
```

- **Orchestrator** (`app/orchestrator.py`): loads the speaker's context, routes to a specialist, and uses the LLM tool-calling brain (`app/llm.py`: Vercel AI Gateway, OpenAI or Anthropic) when `AI_GATEWAY_API_KEY`, `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` is set.
- **Specialist agents** (`app/agents/`): `travel`, `calendar`, `dining`, `school`, `care`, `household`. Each has JSON-schema tools, a rule-based handler, and demo triggers.
- **Voice** (`app/agora.py`): starts a per-member Agora agent with the official `agora-agents` SDK: Agora ASR, this backend as the LLM, and Murf Falcon TTS with the voice from `app/voices.py` (Murf's recommended Indian voices: Pooja, Rachna, Nikhil, Abhinav and more).
- **Notifications** (`app/state.py`): recorded in the app and delivered over Agora Chat when configured.
- **Family Room** (`app/rooms.py`, `app/planner.py`, `app/rooms_api.py`): a shared room where people talk (typing, voice or video over Agora RTC) and Aangan turns the discussion into a plan that builds itself on screen: live flights (`app/live_flights.py`, Kiwi), train, bus and car estimates (`app/ground.py`), a stay, places and meals for each day, and a running cost against the budget. The planner is a tool-calling agent over the plan; it never books: it proposes and the host approves (a clearly marked demo booking).
- **LLM gateway** (`app/gateway.py`): Vercel AI Gateway with fallback across several cheap models when one is rate limited (the free tier allows 5 requests a minute per model).
- **Speed**: clear questions are answered by the rule engine in milliseconds; open ones stream, with a spoken lead-in while tools run.

Plan the demo with `docs/DEMO.md`.

## Connecting the real services

Copy `backend/.env.example` to `backend/.env` and fill it in. The app's Settings screen (and `GET /api/config`) shows exactly which variables are still missing for each service.

| Service | Variables |
|---|---|
| Voice (Agora ConvoAI) | `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE`, `PUBLIC_BASE_URL`, `LLM_API_KEY` |
| Murf Falcon TTS | `MURF_API_KEY` |
| LLM brain (optional, recommended) | `AI_GATEWAY_API_KEY` (or `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) |
| Agora Chat (optional) | `AGORA_CHAT_HOST`, `AGORA_CHAT_APP_ID`, `AGORA_CHAT_APP_TOKEN`, `AGORA_CHAT_TO` |

`PUBLIC_BASE_URL` must be a public HTTPS address for this backend, because Agora calls `/v1/chat/completions` as the agent's LLM. Use an ngrok or cloudflared tunnel to port 8000, or deploy it.

Agora's pricing page lists $0.10 per minute for Conversational AI, with the first 300 minutes free.

## Language mode

`AANGAN_LANGUAGE_MODE` in `backend/.env` (shown by `GET /api/config` as `language_mode`):

- `english`: everything is English for every family member. Replies and greetings are English, speech recognition is `en-IN`, and each member keeps their assigned Murf voice speaking the `en-IN` locale. This is what `render.yaml` sets.
- `multi`: English, Hindi, Telugu and Kannada. Aangan answers in the language that was spoken (detected per turn) and switches the Murf locale to match.
- `native`: each member gets their own language. Hindi and Hinglish speakers get Hinglish replies, recognition is `hi` or `hi-Latn`, and the Murf locale is `hi-IN` or `hi-LATN`.

The mode can also be changed from the app's Settings; that choice is saved with the household.

## What is real and what is not

Real: the Agora voice session and RTC room, Murf Falcon voices, the tool-calling LLM brain, the orchestrator and every agent's logic, the family state and calendar, the Family Room planner, live flight search for the room (Kiwi), and the PWA.

Estimates, labelled as such in the app: train, bus and car fares and journey times (worked out from the distance between cities, no timetables).

Not real, and cannot be without third-party accounts: in the family assistant, flights, restaurants, cabs and the pharmacy are catalogues stored in the agents' seed data (`app/agents/*.py`); in the Family Room, hotels, places and restaurants are sample data (marked *Sample*) and bookings are demo bookings (no money moves). These are the only simulated data. Each agent talks to its catalogue only through its tools, so a real provider can replace one without touching the rest. The demo family (Priya, Rahul, Aarav and Dadi) is seed data in `app/seed.py`; new members are added through the app or by voice.

## Not yet verified against the live services

Verified live:
- The official Agora quickstart (`agora-baseline/`), in English, with Deepgram `nova-3` (`en-IN`), Murf `en-IN-abhinav` and this backend as the LLM through a tunnel: a spoken conversation works end to end.
- `POST /api/agent/start` starts real agents with that same configuration (Agora accepted it for Rahul and Dadi) and `POST /api/agent/stop` stops them.
- Murf synthesises speech for every member's voice in `en-IN` (`en-IN-pooja`, `en-IN-nikhil`, `en-IN-abhinav`, `hi-IN-rachna`) and in their native locales.

Also verified live: speaking into the Family Room from our own PWA (the transcript reaches the planner, which updates the plan and answers), and the planner's whole text flow against the real model and live flights (plan, switch between train, car and flights, propose a booking and wait for approval).

Not yet verified: Hindi, Telugu and Kannada speech recognition and per-turn Murf locale switching with a real microphone, two people speaking at once in the room, and Agora Chat delivery (not configured).

## Deploying

`render.yaml` is a Render blueprint (one Docker container serves the API and the PWA over HTTPS, which the microphone needs). Set `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE`, `MURF_API_KEY` and `AI_GATEWAY_API_KEY` in the dashboard; `LLM_API_KEY` is generated and the public address is taken from Render. The free plan sleeps after 15 minutes idle, so keep it awake with a pinger on `/api/config` before a demo.

## Skills installed for development

Project skills in `.agents/skills/`: Agora's official skill (`AgoraIO/skills`) and Vercel's agent skills (`vercel-labs/agent-skills`: React best practices, composition patterns, web design guidelines and more).
