# Voice Agent — Phone Number Collection

Internship assignment for VAIU AI. A LiveKit voice agent that collects a valid 10-digit Indian mobile number through natural speech (English, Hindi, or mixed), confirms it digit-by-digit, and stores it in a small FastAPI + SQLite backend with a React dashboard.

Parsing is fully deterministic. No LLM is used to guess the phone number.

## Stack

| Layer | Choice |
|---|---|
| Voice runtime | LiveKit Agents 1.8 + Silero VAD |
| STT | Deepgram Nova-3 (`language=multi`) or OpenAI Whisper |
| TTS | ElevenLabs multilingual or OpenAI TTS |
| Noise handling | LiveKit WebRTC APM (NS, AEC, AGC, HPF) + RMS/confidence gate |
| Backend | FastAPI + SQLAlchemy + SQLite |
| Dashboard | React 18 + Vite |

## Project layout

```
voice-phone-agent/
├── agent/           # LiveKit worker + conversation state machine
├── parser/          # parsePhoneNumber() and helpers
├── backend/         # FastAPI + SQLite
├── dashboard/       # React dashboard
├── tests/           # pytest suite
├── .env.example
├── requirements.txt
└── README.md
```

## What it handles

**Grouping:** single digits, pairs, triplets, 5+5 chunks, full number at once.

**Pause / resume:** if fewer than 10 digits are heard, the agent stays quiet for up to 4 seconds so the user can finish, then prompts if still incomplete.

**Self-correction:** markers like `wait`, `sorry`, `nahi`, `scratch that` restart from the corrected part.

**Languages:**
- English — `nine eight seven...`, `oh` → 0
- Hindi — `nau aath saat chhe...`, `shunya` / `sifar` → 0
- Hinglish — `nine aath saat 6 5 chaar...`
- Repetition — `double seven` → 77, `triple nine` → 999

**Validation:** exactly 10 digits, first digit in 6–9. Invalid numbers are never stored.

## Noise cancellation

Incoming mic audio is filtered with LiveKit’s native WebRTC Audio Processing Module before STT:

- Noise suppression for chatter / traffic / room hum
- Echo cancellation so TTS playback does not re-trigger STT
- AGC + high-pass filter for uneven mic levels

After STT, an audio quality gate rejects utterances with very low RMS energy (`< 0.01`) or low STT confidence (`< 0.40`) and re-prompts instead of guessing digits. This matters a lot for Hindi digit words, which degrade quickly under noise.

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- LiveKit + Deepgram + ElevenLabs keys (only needed for the live voice worker)

### 1. Python env

```bash
git clone <your-repo-url>
cd voice-phone-agent

python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Environment

```bash
cp .env.example .env
```

Fill in credentials when running the LiveKit worker. For the offline dialog tester you can leave placeholders.

| Variable | Purpose |
|---|---|
| `LIVEKIT_URL` | LiveKit WebSocket URL |
| `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | LiveKit auth |
| `STT_PROVIDER` | `deepgram` (default) or `openai` |
| `DEEPGRAM_API_KEY` | Deepgram STT |
| `TTS_PROVIDER` | `elevenlabs` (default) or `openai` |
| `ELEVENLABS_API_KEY` | ElevenLabs TTS |
| `OPENAI_API_KEY` | Used if STT/TTS provider is openai |
| `DATABASE_URL` | Default `sqlite:///./phone_agent.db` |
| `BACKEND_URL` | Default `http://localhost:8000` |
| `FRONTEND_URL` | Default `http://localhost:5173` |

### 3. Backend

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

### 4. Dashboard

```bash
cd dashboard
npm install
npm run dev
```

Open http://localhost:5173

### 5. Agent

**Offline tester** (no LiveKit / STT keys required):

```bash
python -m agent.main test
```

**LiveKit worker:**

```bash
python -m agent.main dev
```

## API

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | Liveness |
| `POST` | `/api/phone` | Save validated number |
| `GET` | `/api/phone` | List + search/filter (`search`, `language`, `start_date`, `end_date`) |
| `GET` | `/api/phone/stats` | Totals by language |
| `DELETE` | `/api/phone/{id}` | Delete one record |

`POST` body:

```json
{
  "rawTranscript": "nine eight seven six five four three two one zero",
  "parsedNumber": "9876543210",
  "language": "en"
}
```

Stored fields: `rawTranscript`, `parsedNumber`, `language` (`en` | `hi` | `mixed`), `collectedAt`.

## Parser

`parser/phone_parser.py` exposes `parse_phone_number()` / `parsePhoneNumber(transcript)`.

Rough pipeline:

1. Normalize text
2. Split on correction markers
3. Expand `double` / `triple` / `quadruple`
4. Map English + Hindi digit words (and numeric tokens) to digits
5. Strip optional `91` / leading `0`
6. Classify language
7. Validate Indian mobile format

## Conversation flow

1. Agent greets and asks for the number
2. User speaks (possibly with pauses / corrections)
3. Agent waits on incomplete digit counts (up to 4s silence)
4. On a valid 10-digit number, agent reads it back digit by digit and asks for confirmation
5. On yes / haan — saves via `POST /api/phone`
6. On no / nahi — asks again

## Tests

```bash
pytest -v
```

Covers parser edge cases, validation, language detection, conversation state machine, API routes, and audio quality gate behavior.

## Demo script (2–3 min)

1. Start backend + dashboard, briefly show the folder layout
2. `python -m agent.main test` — English number, confirm with `yes`
3. Hindi: `nau aath saat chhe paanch chaar teen do ek shunya`
4. Pause: speak first half, type `pause`, then finish the digits
5. Self-correction: `nine eight seven wait sorry nine eight six seven five four three two one zero`
6. Dashboard — stats, search, expand transcript, delete a row

## Notes / limits

- Live voice needs real STT/TTS/LiveKit credentials; offline tester covers dialog + DB without them
- Deeper ML denoisers (RNNoise etc.) were skipped in favour of LiveKit’s built-in APM for simpler local setup
- Regional languages beyond Hindi are not mapped yet

## License

MIT — see [LICENSE](LICENSE).
