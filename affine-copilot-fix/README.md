# Affine Copilot Fix

This python script creates a small http server, to handle the Affine Copilot feature with Gemini from Google or any other OpenAI compatible API. Gemini has a free-tier AI API feature.

## Create API Key

To use the Gemini API, you need to obtain an API Key. Visit the following link to create your free Gemini API Key: [Get a free Gemini API Key](https://aistudio.google.com/apikey). 

To use the OpenRouter API, you need to obtain an API Key. Visit the following link to create your free OpenRouter API Key: [Get a free OpenRouter API Key](https://openrouter.ai/settings/keys). 

Once you have the key(s), you can use it to configure the application as described below.

## Docker Installation

I'm using Affine in a docker container. You need to create `config.json` in your volumes and enable the copilot feature. The `baseUrl` must point to your script, and the `apiKey` must be set to anything. But NOT empty.

```bash
nano ./volumes/affine/self-host/config/config.json 
```

Content of my config.json

```json
{
    "$schema": "https://github.com/toeverything/affine/releases/latest/download/config.schema.json",
    "server": {
        "name": "My AFFiNE server"
    },
    "copilot": {
        "enabled": true,
        "providers.openai": {
            "apiKey": "my-not-exist-api-key",
            "baseUrl": "http://affine-copilot-fix:5000"
        },
        "providers.gemini": {
            "apiKey": ""
        }
    }
}
```


Content of my docker-compose.yml


```yml
name: affine
services:
    affine-copilot-fix:
        container_name: affine-copilot-fix
        user: "1000:1000"
        build:
            context: ./affine-copilot-fix
            dockerfile: Dockerfile
        volumes:
            - ./logs:/app/src/logs
        environment:
            - CREATE_LOG=True
            - OPENAI_API_KEY=<ENTER YOUR FREE GEMINI OR OPENROUTER API KEY>
            - OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/ # https://openrouter.ai/api/v1/
            - OPENAI_MODEL=gemini-2.0-flash # Or any openrouter model
        ports:
            - 5000:5000
        image: affine-copilot-fix:latest
        networks:
            - affine-net

    affine:
        image: ghcr.io/toeverything/affine-graphql:${AFFINE_REVISION:-stable}
        ...

```
## What the gateway does

AFFiNE's self-hosted copilot only talks to an `openai` provider and (since
v0.25) uses the **Responses API** (`POST /responses`), falling back to
`/chat/completions` only when `oldApiStyle` is enabled. This gateway accepts
both shapes, re-emits a correct Responses SSE event stream so AFFiNE's OpenAI
SDK parses streamed text reliably, and additionally serves `/embeddings` and
`/images/generations` for the non-chat scenarios.

Endpoints: `/responses`, `/chat/completions`, `/embeddings`,
`/images/generations`, `/models`, `/health` (each also under `/v1/...`).

## Scenario routing (optional, multi-provider)

By default every request is forced onto `OPENAI_MODEL` against `OPENAI_BASE_URL`
(the old behaviour). If you want AFFiNE's per-scenario model config to actually
route to different providers/models, use either:

**Inline syntax** — set a scenario's model in AFFiNE to `provider:model`:

```
openrouter:anthropic/claude-3.5-sonnet
```

with the provider defined via the `PROVIDERS` env var.

**Routes table** — map the model string AFFiNE sends to a provider + model:

```env
PROVIDERS='{"openrouter":{"base_url":"https://openrouter.ai/api/v1","api_key":"sk-or-..."}}'
MODEL_ROUTES='{"gpt-4o-2024-08-06":{"provider":"openrouter","model":"openai/gpt-4o"}}'
```

`embedding` and `image` scenarios always pass AFFiNE's model id through
unchanged (e.g. `gemini-embedding-001`), since those are real target models.
See `src/.env.example` for all options.

## Optional: run on your Claude / Codex / Gemini subscription (ACP sidecar)

A companion service, [`affine-acp`](../affine-acp), lets the text scenarios run on a
coding agent over **ACP** (Claude Code / Codex / Gemini CLI) using your existing
**subscription login** instead of an API key.

It works **only together with this gateway** — AFFiNE always talks to this gateway,
which routes the agent scenarios to the sidecar and keeps `embedding` / `image` /
`audio` on a real API (the sidecar can't do those). You point a provider's
`base_url` at the sidecar and add a route:

```jsonc
PROVIDERS   = {"claude":{"base_url":"http://affine-acp:5100/claude/v1","api_key":"acp"}}
MODEL_ROUTES = {"gpt-5-mini":{"provider":"claude","model":"sonnet"},
                "gpt-5":     {"provider":"claude","model":"opus"}}
```

Then set a scenario to `gpt-5-mini` (→ Claude Sonnet) or `gpt-5` (→ Claude Opus).
See [`affine-acp/README.md`](../affine-acp/README.md) for agents, auth, model
switching and limitations.

## Restart Docker Container

You need to use the `--force-recreate` flag to force to read your new config.json

```bash
docker compose up -d --force-recreate 
```

## Installation without Docker

### Switch to Source Directory
``` bash
cd ./src
```

Create .env file and change your settings

```
cp .env.example .env
```



### Set Up a Python Virtual Environment

```bash
python -m venv myenv
```
    

### Activate virtual env

#### On Windows:

```bash
myenv\Scripts\activate
```

#### On Mac/Linux:

```bash
source myenv/bin/activate
```

## Install requirements

```
pip install -r requirements.txt
```


## Run your server

To start the server, run the following command:

```bash
python endpoint.py
```