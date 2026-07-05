# AFFiNE Copilot Fix

Two small companion services that free the **AFFiNE** self-hosted copilot from its
built-in provider restrictions. AFFiNE talks to the gateway as its "openai"
provider; the gateway routes each scenario wherever you want.

| Folder | Service | What it does |
| ------ | ------- | ------------ |
| [`affine-copilot-fix/`](affine-copilot-fix) | **gateway** (Python/Flask) | OpenAI-compatible endpoint AFFiNE points at. Emulates the Responses API, routes each scenario to a provider/model, and proxies `embeddings` / `images` to a real API. |
| [`affine-acp/`](affine-acp) | **ACP sidecar** (Node) — *optional* | Runs the **text** scenarios on a coding agent over ACP (**Claude Code / Codex / Gemini CLI**) using your **subscription login** instead of an API key. |

```
AFFiNE ──OpenAI/Responses──► affine-copilot-fix ──┬─► real OpenAI-compatible API
                              (gateway, required)  │   (embeddings, images, chat…)
                                                   └─► affine-acp ──► Claude / Codex / Gemini
                                                       (optional)     (your subscription, via ACP)
```

## Which do I need?

* **Just want any OpenAI-compatible API** (e.g. Gemini free tier, OpenRouter) behind
  AFFiNE, with per-scenario model routing? → the **gateway alone** is enough.
* **Want text scenarios on your Claude / Codex / Gemini subscription?** → add the
  **ACP sidecar**. It only works together with the gateway — AFFiNE never talks to
  it directly.

## Quick start

1. Point AFFiNE's `providers.openai.baseUrl` at the gateway (`http://affine-copilot-fix:5000`).
2. Configure the gateway — see [`affine-copilot-fix/README.md`](affine-copilot-fix/README.md).
3. *(optional)* Add the ACP sidecar — see [`affine-acp/README.md`](affine-acp/README.md).

A ready-to-adapt [`docker-compose.yml`](docker-compose.yml) builds both services.

## Not affiliated with AFFiNE, Anthropic, OpenAI, or Google.
