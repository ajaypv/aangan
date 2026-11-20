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

- `english` (default): everything is English for every family member. Replies and greetings are English, speech recognition is `en-IN`, and each member keeps their assigned Murf voice speaking the `en-IN` locale.
- `native`: each member gets their own language. Hindi and Hinglish speakers get Hinglish replies, recognition is `hi` or `hi-Latn`, and the Murf locale is `hi-IN` or `hi-LATN`.

## What is real and what is not

Real: the Agora voice session, Murf voices, Claude tool-calling brain, Agora Chat delivery, the orchestrator and every agent's logic, the family state and calendar, and the PWA.

Not real, and cannot be without third-party accounts: flights, restaurants, cabs and the pharmacy are catalogues stored in the agents' seed data (`app/agents/*.py`). They are the only simulated data. Each agent talks to its catalogue only through its tools, so a real provider can replace one without touching the rest. The demo family (Priya, Rahul, Aarav and Dadi) is seed data in `app/seed.py`; new members are added through the app or by voice.

## Not yet verified against the live services

Verified live:
- The official Agora quickstart (`agora-baseline/`), in English, with Deepgram `nova-3` (`en-IN`), Murf `en-IN-abhinav` and this backend as the LLM through a tunnel: a spoken conversation works end to end.
- `POST /api/agent/start` starts real agents with that same configuration (Agora accepted it for Rahul and Dadi) and `POST /api/agent/stop` stops them.
- Murf synthesises speech for every member's voice in `en-IN` (`en-IN-pooja`, `en-IN-nikhil`, `en-IN-abhinav`, `hi-IN-rachna`) and in their native locales.

Not yet verified: audio through our own PWA client (the browser side is still being built against the start-response contract), Hindi and Hinglish speech recognition in native mode, Agora Chat delivery, and the Claude loop against the real API (it passes with a fake client).

## Skills installed for development

Project skills in `.agents/skills/`: Agora's official skill (`AgoraIO/skills`) and Vercel's agent skills (`vercel-labs/agent-skills`: React best practices, composition patterns, web design guidelines and more).
