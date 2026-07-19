# AI Phone Interpreter (India)

A real-time voice call app where two users speaking different languages
(Telugu, Hindi, English, and their code-mixed forms Tenglish/Hinglish) can
talk naturally. The system transcribes, understands the *meaning* of what's
said, and speaks it back in the listener's preferred language/mode - not a
word-for-word translation, but a natural, context-aware one.

## Architecture at a Glance

This is a **microservices** system. Each stage of the audio pipeline is an
independently deployable service:

```
audio_service -> speech_service -> language_service -> translation_service -> tts_service
                                          ^
                                          |
                                conversation_service (context)
```

All orchestration, auth, and client-facing signaling goes through
`api_gateway`. Services communicate over **Redis Streams**. Durable data
(users, call history, transcripts) lives in **PostgreSQL**.

See [`docs/architecture/`](docs/architecture) for diagrams and
[`docs/phase-notes/`](docs/phase-notes) for the running log of design
decisions made in each build phase.

## Project Structure

```
AI-Interpreter/
├── mobile/                # Flutter client app
├── backend/
│   ├── api_gateway/        # Auth, signaling, orchestration (FastAPI)
│   ├── audio_service/      # Noise reduction, echo cancellation, VAD
│   ├── speech_service/     # Streaming Speech-to-Text
│   ├── language_service/   # Language + mixed-language detection
│   ├── translation_service/# Meaning-preserving, context-aware translation
│   ├── tts_service/        # Streaming Text-to-Speech
│   ├── conversation_service/# Conversation context & history
│   └── shared/             # Schemas, messaging abstraction, logging - used by all services
├── database/                # SQL schema + Alembic migrations
├── docker/                  # docker-compose files, nginx/TURN config
└── docs/                    # Architecture docs, API docs, phase notes
```

## Local Development Quick Start

1. Copy the environment template and fill in secrets:
   ```bash
   cp .env.example .env
   ```
2. Bring up the full stack:
   ```bash
   docker compose -f docker/docker-compose.yml --env-file .env up --build
   ```
3. Check every service is healthy:
   ```bash
   curl http://localhost:8000/health   # api_gateway
   curl http://localhost:8001/health   # audio_service
   curl http://localhost:8002/health   # speech_service
   curl http://localhost:8003/health   # language_service
   curl http://localhost:8004/health   # translation_service
   curl http://localhost:8005/health   # tts_service
   curl http://localhost:8006/health   # conversation_service
   ```

Each should return `{"service": "<name>", "status": "ok"}`.

# 🚀 Project Status

| Phase | Status |
|-------|--------|
| Phase 1 – System Architecture & Backend Connectivity | ✅ Completed |
| Phase 2 – Flutter Project Skeleton | ✅ Completed |
| Phase 3 – Flutter User Interface | ⏳ Planned |
| Phase 4 – Authentication | ⏳ Planned |
| Phase 5 – Speech-to-Text | ⏳ Planned |
| Phase 6 – Translation | ⏳ Planned |
| Phase 7 – Text-to-Speech | ⏳ Planned |
| Phase 8 – Real-Time Calling | ⏳ Planned |

## Tech Stack

| Layer | Technology |
|---|---|
| Mobile client | Flutter |
| Backend | Python, FastAPI |
| Real-time media | WebRTC |
| Inter-service messaging | Redis Streams |
| Database | PostgreSQL |
| Containerization | Docker / Docker Compose |

## Current Progress

### ✅ Completed

- Project architecture
- Dockerized microservices
- FastAPI API Gateway
- PostgreSQL setup
- Redis setup
- Flutter project skeleton
- Flutter ↔ Backend connectivity
- Health monitoring endpoints

### 🚧 In Progress

- Flutter UI

### 📅 Planned

- Authentication
- Speech-to-Text
- Translation
- Text-to-Speech
- Real-time audio streaming
