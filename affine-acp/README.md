# affine-acp

An OpenAI-compatible bridge that lets the **AFFiNE** self-hosted copilot run on a
coding agent over **ACP** (Agent Client Protocol) — **Claude Code**, **Codex**, or
**Gemini CLI** — using your existing *subscription login* instead of a per-token
API key.

> **Requires the [`affine-copilot-fix`](../affine-copilot-fix) gateway — it does not
> work on its own.** AFFiNE never talks to this sidecar directly. AFFiNE talks to
> the gateway (its "openai" provider), and the gateway routes the *text* scenarios
> here while keeping embeddings / images / audio on a real API. Run both together.

It pairs with that OpenAI-compatible gateway, which AFFiNE talks to as its "openai"
provider. This sidecar is only the agent backend behind it.

```
AFFiNE  ──HTTP(OpenAI Responses)──►  gateway (affine-copilot-fix)
                                         │  routes by model name
                                         ▼
                              affine-acp (this service)
                                         │  spawns an ACP agent (stdio JSON-RPC)
                                         ▼
                        claude-agent-acp / codex-acp / gemini --experimental-acp
                                         │
                                         ▼
                     Claude / Codex / Gemini  (your subscription)
```

Nothing in AFFiNE itself is modified — AFFiNE only knows a `baseUrl` pointing at
the gateway and speaks plain OpenAI to it.

---

## How it works

* The sidecar exposes an OpenAI `POST /chat/completions` endpoint, one per agent,
  selected by URL path: `/<agent>/v1/chat/completions` (e.g. `/claude/v1/...`).
* On each request it spawns (and reuses) the ACP agent as a subprocess, speaks
  JSON-RPC 2.0 over stdio (`initialize` → `session/new` → `session/prompt`), and
  streams the agent's text (`agent_message_chunk`) back as OpenAI chunks.
* Tool-use / filesystem permission requests from the agent are **declined**, so
  the agent answers as a plain text model (no file edits, no shell).
* A separate agent process is spawned per **(agent, model)** pair, so the model
  is selectable per request.

---

## Switching the LLM

Because AFFiNE decides which provider to use **by the model name**, switching the
model is a three-layer mapping. Once set up, you switch models by editing config —
no code changes.

### Layer 1 — AFFiNE scenario → model name

In AFFiNE **Admin → Settings → AI**, the "custom models in scenarios" box maps each
scenario to a model name. AFFiNE only forwards a name to the OpenAI provider (the
gateway) if it **recognizes it as an OpenAI model** (e.g. `gpt-5`, `gpt-5-mini`,
`gpt-4o`, `gpt-4o-2024-08-06`, `gpt-4.1`). Arbitrary names like `claude:sonnet` are
rejected by AFFiNE (`NO_COPILOT_PROVIDER_AVAILABLE`).

```json
{"scenarios":{"chat":"gpt-5-mini","complex_text_generation":"gpt-5"},"override_enabled":true}
```

### Layer 2 — gateway `MODEL_ROUTES` → provider + agent model

The gateway re-routes those recognized names to an agent and a concrete model:

```jsonc
// MODEL_ROUTES (env on the gateway service)
{
  "gpt-5-mini": { "provider": "claude", "model": "sonnet" },  // fast / cheaper
  "gpt-5":      { "provider": "claude", "model": "opus"   },  // strongest
  "gpt-5-codex":{ "provider": "codex",  "model": ""       }   // "" = agent default
}
```

`provider` refers to a `PROVIDERS` entry whose `base_url` points at this sidecar,
e.g. `{"claude":{"base_url":"http://affine-acp:5100/claude/v1","api_key":"acp"}}`.

### Layer 3 — sidecar → agent model

The sidecar injects `model` into the agent process:

| Agent  | Mechanism            | Example model values          |
| ------ | -------------------- | ----------------------------- |
| claude | `ANTHROPIC_MODEL` env | `sonnet`, `opus`, `haiku`, or a full id |
| codex  | `CODEX_MODEL` env     | agent default, or a model id  |
| gemini | `--model` flag        | `gemini-2.5-pro`, `gemini-2.5-flash` |

**To switch the model for a scenario:** change the name in AFFiNE (Layer 1) to one
that maps to the agent/model you want in `MODEL_ROUTES` (Layer 2). To add a new
choice, add a `MODEL_ROUTES` entry and use its name in AFFiNE.

---

## Agents & authentication

Each agent is a normal CLI that authenticates with your subscription. Log in on the
host, then bind-mount its credential directory into the sidecar (same UID). All
three are the packages used by the Obsidian *agent-client* plugin.

| Agent  | Package (installed in image)         | Launch                     | Credentials dir |
| ------ | ------------------------------------ | -------------------------- | --------------- |
| claude | `@agentclientprotocol/claude-agent-acp` | `claude-agent-acp`      | `~/.claude`     |
| codex  | `@zed-industries/codex-acp` (+ `@openai/codex`) | `codex-acp`     | `~/.codex`      |
| gemini | `@google/gemini-cli`                 | `gemini --experimental-acp`| `~/.gemini`     |

Agents are configurable via the `AGENTS` env var (JSON) if you need different
commands, env vars, or a default model.

---

## Example `docker-compose.yml`

Sanitized, self-contained. Replace `/path/to` and the API key placeholder.

```yaml
services:
  affine-acp:
    build: ./affine-acp
    environment:
      - PORT=5100
      - HOME=/home/node
      - ACP_CWD=/tmp
    volumes:
      # your subscription logins, mounted so tokens can refresh
      - /path/to/.claude:/home/node/.claude
      # - /path/to/.codex:/home/node/.codex
      # - /path/to/.gemini:/home/node/.gemini
    # no public ports needed; the gateway reaches it on the internal network

  affine-copilot-fix:               # the OpenAI-compatible gateway AFFiNE talks to
    build: ./affine-copilot-fix
    environment:
      # non-agent scenarios (embeddings, etc.) fall back to this provider:
      - OPENAI_API_KEY=your-embeddings-provider-key
      - OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
      - OPENAI_MODEL=gemini-2.5-flash-lite
      - 'PROVIDERS={"claude":{"base_url":"http://affine-acp:5100/claude/v1","api_key":"acp"},"codex":{"base_url":"http://affine-acp:5100/codex/v1","api_key":"acp"}}'
      - 'MODEL_ROUTES={"gpt-5-mini":{"provider":"claude","model":"sonnet"},"gpt-5":{"provider":"claude","model":"opus"},"gpt-5-codex":{"provider":"codex","model":""}}'
    ports:
      - 5000:5000
    depends_on:
      - affine-acp
```

Point AFFiNE's `providers.openai.baseUrl` at `http://affine-copilot-fix:5000`.

---

## Verifying

```bash
# health
curl http://localhost:5100/health          # {"status":"ok","agents":[...]}

# talk to an agent directly (bypasses AFFiNE + gateway)
curl -s http://localhost:5100/claude/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"opus","messages":[{"role":"user","content":"which model are you?"}]}'
```

The sidecar logs each spawn and its model, e.g. `spawning agent 'claude' model='opus'`.

---

## Limitations

* **Text only.** ACP agents cannot do embeddings, image generation, or audio
  transcription — keep those scenarios on a real API (e.g. Gemini) via the gateway.
* **AFFiNE gatekeeps by model name.** You must use a model name AFFiNE recognizes
  for the OpenAI provider; the gateway then re-routes it. Inline `provider:model`
  names are rejected by AFFiNE.
* **Coding-agent behavior.** The agents are coding assistants; answers can be more
  verbose than a plain chat model, and tool/file requests are declined (text-only).
* **Cold start.** The first request to a given (agent, model) spawns a process
  (~5 s); subsequent requests reuse it. Each distinct model is a separate process.
* **Subscription limits apply.** Usage counts against your plan's rate/quota limits.
* **Credential sharing.** Codex (ChatGPT) uses rotating refresh tokens — sharing
  one `~/.codex` between the host and the container can invalidate the token
  (`refresh token already used`); re-run `codex login` and avoid concurrent use.
* **Not affiliated** with AFFiNE, Anthropic, OpenAI, or Google.
