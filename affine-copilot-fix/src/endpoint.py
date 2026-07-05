"""
AFFiNE Copilot Fix — OpenAI-compatible gateway.

AFFiNE's self-hosted copilot only speaks to an "openai" provider, and it now
uses the *Responses* API (`POST /responses`, payload with `input`/`max_output_tokens`),
falling back to `/chat/completions` only when `oldApiStyle` is enabled.

This gateway:
  * accepts both the Responses API and Chat Completions shapes from AFFiNE,
  * routes each request to a configurable upstream provider + model
    (so AFFiNE's per-scenario model config actually means something),
  * re-emits a *correct* Responses SSE event sequence so the official OpenAI
    SDK inside AFFiNE parses streamed text reliably,
  * proxies /embeddings and /images/generations for the non-chat scenarios.

Routing (all optional, backward compatible with the old single-provider setup):

  OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
      Define the implicit "default" provider and the fallback model. If nothing
      else is configured this behaves exactly like the old proxy (every request
      forced onto OPENAI_MODEL against OPENAI_BASE_URL).

  PROVIDERS  (JSON)
      Named upstreams, e.g.
        {"gemini":   {"base_url":"https://generativelanguage.googleapis.com/v1beta/openai/","api_key":"..."},
         "openrouter":{"base_url":"https://openrouter.ai/api/v1","api_key":"..."}}

  MODEL_ROUTES  (JSON)
      Map the model string AFFiNE sends -> {"provider":"gemini","model":"gemini-2.5-flash"}.

  Inline syntax (no table needed): set a scenario's model in AFFiNE to
      "provider:model"  e.g. "openrouter:anthropic/claude-3.5-sonnet"
  and it is routed to that provider with that model.

  DEFAULT_PROVIDER   name of the provider used when nothing matches (default: "default")
  DEFAULT_MODEL      model used when the incoming model is unmapped (default: OPENAI_MODEL)
  PASSTHROUGH_MODEL  if true, unmapped requests keep AFFiNE's model string instead
                     of being rewritten to DEFAULT_MODEL (default: false)
"""

from flask import Flask, request, jsonify, Response, stream_with_context
import json
from datetime import datetime
from dotenv import load_dotenv
import os
import time
import uuid
import openai

load_dotenv()
app = Flask(__name__)


def _as_bool(x, default=False):
    if x is None:
        return default
    return str(x).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _load_json_env(name, default):
    raw = os.getenv(name)
    if not raw or not raw.strip():
        return default
    try:
        return json.loads(raw)
    except Exception as e:
        print(f"[WARN] {name} is not valid JSON ({e}); ignoring.", flush=True)
        return default


CREATE_LOG = _as_bool(os.getenv("CREATE_LOG"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")

# ---- Provider + routing configuration -------------------------------------
PROVIDERS = _load_json_env("PROVIDERS", {})
# Always expose a "default" provider derived from the classic OPENAI_* envs so
# the old single-backend configuration keeps working untouched.
PROVIDERS.setdefault("default", {"base_url": OPENAI_BASE_URL, "api_key": OPENAI_API_KEY})

MODEL_ROUTES = _load_json_env("MODEL_ROUTES", {})
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "default")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", OPENAI_MODEL)
PASSTHROUGH_MODEL = _as_bool(os.getenv("PASSTHROUGH_MODEL"))

LOG_PATH = "logs"
home_directory = os.path.dirname(__file__)
log_directory = os.path.join(home_directory, LOG_PATH)
os.makedirs(log_directory, exist_ok=True)

# Cache OpenAI clients per (base_url, api_key) so we don't rebuild httpx pools.
_CLIENT_CACHE = {}


def _debug(msg):
    print(f"[DEBUG] {datetime.now().isoformat()} - {msg}", flush=True)


def _provider_cfg(name):
    cfg = PROVIDERS.get(name)
    if cfg is None:
        cfg = PROVIDERS.get("default", {})
    return cfg


def resolve_route(incoming_model, passthrough=None):
    """
    Map the model string AFFiNE sends to (provider_name, provider_cfg, target_model).

    Precedence: inline "provider:model" > MODEL_ROUTES table > default provider.

    `passthrough` controls what happens to an *unmapped* model on the default
    provider: when True the incoming model string is kept (correct for
    /embeddings and /images, where AFFiNE already sends a real target model);
    when False it is rewritten to DEFAULT_MODEL (correct for chat/responses,
    where AFFiNE sends models like "gpt-5-mini" the backend doesn't have).
    None falls back to the global PASSTHROUGH_MODEL setting.
    """
    if passthrough is None:
        passthrough = PASSTHROUGH_MODEL
    model = (incoming_model or "").strip()

    # 1) inline "provider:model" syntax
    if ":" in model:
        prov, _, rest = model.partition(":")
        prov = prov.strip()
        rest = rest.strip()
        # only treat as routing if the prefix is a known provider (avoid eating
        # model ids that legitimately contain a colon)
        if prov in PROVIDERS and rest:
            return prov, _provider_cfg(prov), rest

    # 2) explicit routes table
    route = MODEL_ROUTES.get(model)
    if isinstance(route, dict):
        prov = route.get("provider", DEFAULT_PROVIDER)
        target = route.get("model") or model or DEFAULT_MODEL
        return prov, _provider_cfg(prov), target
    if isinstance(route, str) and route:
        # shorthand: "model_string": "just-the-target-model" on the default provider
        return DEFAULT_PROVIDER, _provider_cfg(DEFAULT_PROVIDER), route

    # 3) default provider
    if passthrough and model:
        target = model
    else:
        target = DEFAULT_MODEL or model
    return DEFAULT_PROVIDER, _provider_cfg(DEFAULT_PROVIDER), target


def get_client(provider_cfg):
    base_url = (provider_cfg or {}).get("base_url") or None
    api_key = (provider_cfg or {}).get("api_key") or OPENAI_API_KEY or "not-needed"
    key = (base_url, api_key)
    client = _CLIENT_CACHE.get(key)
    if client is None:
        client = openai.OpenAI(api_key=api_key, base_url=base_url) if base_url \
            else openai.OpenAI(api_key=api_key)
        _CLIENT_CACHE[key] = client
    return client


# passthrough keys for chat.completions
PASSTHRU_KEYS = {
    "temperature", "top_p", "n",
    "stop", "presence_penalty", "frequency_penalty",
    "logit_bias", "seed", "tools", "tool_choice",
    "function_call", "functions", "response_format",
    "max_tokens", "user", "reasoning_effort", "parallel_tool_calls",
}


def _err_payload(message, type_="server_error", code=None, status=500):
    return jsonify({"error": {"message": message, "type": type_, "param": None, "code": code}}), status


def _log_request(data, tag, route_info=None):
    if not CREATE_LOG:
        return
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fname = f"{tag}.log" if tag else "chat.log"
        with open(os.path.join(log_directory, fname), "a", encoding="utf-8") as f:
            f.write(f"\n=== {ts} ===\n")
            if route_info:
                f.write(f"Route: {route_info}\n")
            f.write(f"IP: {request.remote_addr}\n")
            f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Logging failed: {e}", flush=True)


# ---- message conversion ---------------------------------------------------

def _convert_content(content):
    """
    Normalize a single message's content into something the Chat Completions API
    accepts. Preserves multimodal parts (text + images) instead of flattening,
    so AFFiNE's vision scenarios keep working.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if not isinstance(item, dict):
                if isinstance(item, str):
                    parts.append({"type": "text", "text": item})
                continue
            itype = item.get("type")
            if itype in ("text", "input_text", "output_text"):
                parts.append({"type": "text", "text": item.get("text", "")})
            elif itype in ("image_url", "input_image"):
                url = item.get("image_url") or item.get("url") or item.get("image")
                if isinstance(url, dict):
                    parts.append({"type": "image_url", "image_url": url})
                elif isinstance(url, str):
                    parts.append({"type": "image_url", "image_url": {"url": url}})
            elif "text" in item and isinstance(item["text"], str):
                parts.append({"type": "text", "text": item["text"]})
            elif "content" in item and isinstance(item["content"], str):
                parts.append({"type": "text", "text": item["content"]})
        # collapse to a plain string when there's only text (widest compat)
        if parts and all(p.get("type") == "text" for p in parts):
            return "\n".join(p["text"] for p in parts)
        return parts
    return str(content)


def _role_map(role):
    if role in ("developer", "system"):
        return "system"
    if role in ("user", "assistant", "tool", "function"):
        return role
    return "user"


def _convert_to_openai_messages(data):
    """
    Accept either OpenAI Chat Completions {"messages":[...]} or the Responses
    shape {"input": "..."} / {"input":[{"role","content"}...]} / {"instructions", "input"}.
    """
    messages = []

    instructions = data.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        messages.append({"role": "system", "content": instructions})

    if "messages" in data and isinstance(data["messages"], list):
        for m in data["messages"]:
            if isinstance(m, dict):
                messages.append({
                    "role": _role_map(m.get("role", "user")),
                    "content": _convert_content(m.get("content", "")),
                })
        if not messages:
            raise ValueError("No messages provided.")
        return messages

    inp = data.get("input")
    if isinstance(inp, str):
        messages.append({"role": "user", "content": inp})
        return messages
    if isinstance(inp, list):
        for item in inp:
            if not isinstance(item, dict):
                continue
            messages.append({
                "role": _role_map(item.get("role", "user")),
                "content": _convert_content(item.get("content", "")),
            })
        if not messages:
            raise ValueError("No messages provided.")
        return messages

    if messages:  # only had instructions
        return messages
    raise ValueError("No messages provided.")


def _build_upstream_params(data):
    params = {}
    for k in PASSTHRU_KEYS:
        if k in data:
            params[k] = data[k]
    # Responses -> Chat token-limit key
    if "max_output_tokens" in data and "max_tokens" not in params:
        params["max_tokens"] = data["max_output_tokens"]
    return params


def _map_error(e, tag):
    _debug(f"[{tag}] {type(e).__name__}: {e}")
    if isinstance(e, openai.RateLimitError):
        return _err_payload(f"Rate limit exceeded: {e}", type_="rate_limit_error", status=429)
    if isinstance(e, openai.AuthenticationError):
        return _err_payload(str(e), type_="authentication_error", status=401)
    if isinstance(e, openai.PermissionDeniedError):
        return _err_payload(str(e), type_="permission_error", status=403)
    if isinstance(e, openai.BadRequestError):
        return _err_payload(str(e), type_="invalid_request_error", status=400)
    if isinstance(e, openai.APIConnectionError):
        return _err_payload(f"Failed to connect to API: {e}", type_="api_connection_error", status=502)
    return _err_payload(f"Unexpected error: {e}", status=500)


# ===========================================================================
# /chat/completions  (oldApiStyle path + generic OpenAI clients)
# ===========================================================================
@app.route("/chat/completions", methods=["POST"])
@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    try:
        data = request.get_json(force=True, silent=False) or {}
    except Exception:
        return _err_payload("Invalid JSON body.", type_="invalid_request_error", status=400)

    try:
        messages = _convert_to_openai_messages(data)
    except ValueError as e:
        return _err_payload(str(e), type_="invalid_request_error", status=400)

    stream = bool(data.get("stream", False))
    prov_name, prov_cfg, model = resolve_route(data.get("model"))
    if not model:
        return _err_payload("No target model resolved (set OPENAI_MODEL/DEFAULT_MODEL or a route).",
                            type_="invalid_request_error", status=400)

    route_info = f"{prov_name} -> {model} (from '{data.get('model')}')"
    _log_request(data, tag="chat_completions", route_info=route_info)
    _debug(f"[chat] {route_info} | stream={stream}")

    params = _build_upstream_params(data)
    params["model"] = model
    params["messages"] = messages

    try:
        client = get_client(prov_cfg)

        if stream:
            def gen():
                try:
                    s = client.chat.completions.create(stream=True, **params)
                    for chunk in s:
                        ch = chunk.choices[0] if chunk.choices else None
                        delta = {}
                        if ch is not None:
                            if getattr(ch.delta, "role", None):
                                delta["role"] = ch.delta.role
                            if getattr(ch.delta, "content", None) is not None:
                                delta["content"] = ch.delta.content
                            tc = getattr(ch.delta, "tool_calls", None)
                            if tc is not None:
                                try:
                                    delta["tool_calls"] = [t.model_dump() for t in tc]
                                except Exception:
                                    delta["tool_calls"] = tc
                        payload = {
                            "id": getattr(chunk, "id", None),
                            "object": "chat.completion.chunk",
                            "created": getattr(chunk, "created", int(time.time())),
                            "model": getattr(chunk, "model", model),
                            "choices": [{
                                "index": ch.index if ch is not None else 0,
                                "delta": delta,
                                "finish_reason": ch.finish_reason if ch is not None else None,
                            }],
                        }
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception as e:
                    _debug(f"[chat] streaming error: {e}")
                    yield f"data: {json.dumps({'error': {'message': f'Unexpected error: {e}', 'type': 'server_error'}})}\n\n"
                    yield "data: [DONE]\n\n"

            resp = Response(stream_with_context(gen()), mimetype="text/event-stream")
            resp.headers["Cache-Control"] = "no-cache, no-transform"
            resp.headers["X-Accel-Buffering"] = "no"
            return resp

        resp = client.chat.completions.create(**params)
        out = {
            "id": resp.id,
            "object": "chat.completion",
            "created": resp.created or int(time.time()),
            "model": resp.model or model,
            "choices": [],
            "usage": None,
        }
        for i, ch in enumerate(resp.choices):
            try:
                msg = ch.message.model_dump()
            except Exception:
                msg = {"role": "assistant", "content": str(getattr(ch, "message", ""))}
            out["choices"].append({"index": i, "message": msg, "finish_reason": ch.finish_reason})
        try:
            out["usage"] = resp.usage.model_dump() if getattr(resp, "usage", None) else None
        except Exception:
            pass
        return jsonify(out)

    except Exception as e:
        return _map_error(e, "chat")


# ===========================================================================
# /responses  (Responses API shape — the path AFFiNE uses by default)
# ===========================================================================

def _usage_to_responses(usage):
    if not usage:
        return None
    try:
        u = usage.model_dump()
    except Exception:
        u = usage if isinstance(usage, dict) else {}
    return {
        "input_tokens": u.get("prompt_tokens", u.get("input_tokens", 0)),
        "output_tokens": u.get("completion_tokens", u.get("output_tokens", 0)),
        "total_tokens": u.get("total_tokens", 0),
    }


def _base_response_obj(resp_id, model, status, output=None, usage=None):
    return {
        "id": resp_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": status,
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "max_output_tokens": None,
        "model": model,
        "output": output if output is not None else [],
        "parallel_tool_calls": True,
        "temperature": None,
        "tool_choice": "auto",
        "tools": [],
        "top_p": None,
        "usage": usage,
        "metadata": {},
    }


def _responses_stream_adapter(chunks_iter, model):
    """
    Adapt an OpenAI Chat Completions stream into the full Responses-API SSE
    event sequence expected by the official OpenAI SDK (used inside AFFiNE).
    Each frame is emitted as `event: <type>` + `data: <json>`.
    """
    resp_id = f"resp_{uuid.uuid4().hex}"
    item_id = f"msg_{uuid.uuid4().hex}"
    seq = 0
    full_text = []
    usage = None
    finish_reason = None

    def frame(etype, payload):
        nonlocal seq
        payload = dict(payload)
        payload["type"] = etype
        payload["sequence_number"] = seq
        seq += 1
        return f"event: {etype}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    created = _base_response_obj(resp_id, model, "in_progress")
    yield frame("response.created", {"response": created})
    yield frame("response.in_progress", {"response": created})

    item_stub = {"id": item_id, "type": "message", "status": "in_progress",
                 "role": "assistant", "content": []}
    yield frame("response.output_item.added", {"output_index": 0, "item": item_stub})
    yield frame("response.content_part.added", {
        "item_id": item_id, "output_index": 0, "content_index": 0,
        "part": {"type": "output_text", "text": "", "annotations": []},
    })

    for chunk in chunks_iter:
        if getattr(chunk, "usage", None):
            usage = chunk.usage
        if not chunk.choices:
            continue
        ch = chunk.choices[0]
        if ch.finish_reason:
            finish_reason = ch.finish_reason
        piece = getattr(ch.delta, "content", None)
        if not piece:
            continue
        full_text.append(piece)
        yield frame("response.output_text.delta", {
            "item_id": item_id, "output_index": 0, "content_index": 0, "delta": piece,
        })

    text = "".join(full_text)
    yield frame("response.output_text.done", {
        "item_id": item_id, "output_index": 0, "content_index": 0, "text": text,
    })
    part = {"type": "output_text", "text": text, "annotations": []}
    yield frame("response.content_part.done", {
        "item_id": item_id, "output_index": 0, "content_index": 0, "part": part,
    })
    done_item = {"id": item_id, "type": "message", "status": "completed",
                 "role": "assistant", "content": [part]}
    yield frame("response.output_item.done", {"output_index": 0, "item": done_item})

    completed = _base_response_obj(resp_id, model, "completed",
                                   output=[done_item], usage=_usage_to_responses(usage))
    yield frame("response.completed", {"response": completed})


@app.route("/responses", methods=["POST"])
@app.route("/v1/responses", methods=["POST"])
def responses_route():
    try:
        data = request.get_json(force=True, silent=False) or {}
    except Exception:
        return _err_payload("Invalid JSON body.", type_="invalid_request_error", status=400)

    try:
        messages = _convert_to_openai_messages(data)
    except ValueError as e:
        return _err_payload(str(e), type_="invalid_request_error", status=400)

    stream = bool(data.get("stream", False))
    prov_name, prov_cfg, model = resolve_route(data.get("model"))
    if not model:
        return _err_payload("No target model resolved (set OPENAI_MODEL/DEFAULT_MODEL or a route).",
                            type_="invalid_request_error", status=400)

    route_info = f"{prov_name} -> {model} (from '{data.get('model')}')"
    _log_request(data, tag="responses", route_info=route_info)
    _debug(f"[responses] {route_info} | stream={stream}")

    params = _build_upstream_params(data)
    params["model"] = model
    params["messages"] = messages

    try:
        client = get_client(prov_cfg)

        if stream:
            def gen():
                try:
                    s = client.chat.completions.create(stream=True, **params)
                    for line in _responses_stream_adapter(s, model):
                        yield line
                except Exception as e:
                    _debug(f"[responses] streaming error: {e}")
                    err = {"type": "error", "code": "server_error",
                           "message": f"Unexpected error: {e}", "sequence_number": 0}
                    yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n"

            resp = Response(stream_with_context(gen()), mimetype="text/event-stream")
            resp.headers["Cache-Control"] = "no-cache, no-transform"
            resp.headers["X-Accel-Buffering"] = "no"
            return resp

        resp = client.chat.completions.create(**params)
        text = "".join((c.message.content or "") for c in resp.choices if c.message)
        item = {
            "id": f"msg_{uuid.uuid4().hex}", "type": "message", "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }
        payload = _base_response_obj(f"resp_{uuid.uuid4().hex}", resp.model or model,
                                     "completed", output=[item],
                                     usage=_usage_to_responses(getattr(resp, "usage", None)))
        return jsonify(payload)

    except Exception as e:
        return _map_error(e, "responses")


# ===========================================================================
# /embeddings  (AFFiNE "embedding" scenario)
# ===========================================================================
@app.route("/embeddings", methods=["POST"])
@app.route("/v1/embeddings", methods=["POST"])
def embeddings_route():
    try:
        data = request.get_json(force=True, silent=False) or {}
    except Exception:
        return _err_payload("Invalid JSON body.", type_="invalid_request_error", status=400)

    if "input" not in data:
        return _err_payload("No 'input' provided.", type_="invalid_request_error", status=400)

    # Embeddings: AFFiNE already sends a real embedding model id -> keep it.
    prov_name, prov_cfg, model = resolve_route(data.get("model"), passthrough=True)
    route_info = f"{prov_name} -> {model} (from '{data.get('model')}')"
    _log_request(data, tag="embeddings", route_info=route_info)
    _debug(f"[embeddings] {route_info}")

    params = {"model": model, "input": data["input"]}
    for k in ("encoding_format", "dimensions", "user"):
        if k in data:
            params[k] = data[k]

    try:
        client = get_client(prov_cfg)
        resp = client.embeddings.create(**params)
        try:
            return jsonify(resp.model_dump())
        except Exception:
            return jsonify(resp)
    except Exception as e:
        return _map_error(e, "embeddings")


# ===========================================================================
# /images/generations  (AFFiNE "image" scenario) — best effort passthrough
# ===========================================================================
@app.route("/images/generations", methods=["POST"])
@app.route("/v1/images/generations", methods=["POST"])
def images_route():
    try:
        data = request.get_json(force=True, silent=False) or {}
    except Exception:
        return _err_payload("Invalid JSON body.", type_="invalid_request_error", status=400)

    if "prompt" not in data:
        return _err_payload("No 'prompt' provided.", type_="invalid_request_error", status=400)

    # Images: AFFiNE already sends a real image model id -> keep it.
    prov_name, prov_cfg, model = resolve_route(data.get("model"), passthrough=True)
    route_info = f"{prov_name} -> {model} (from '{data.get('model')}')"
    _log_request(data, tag="images", route_info=route_info)
    _debug(f"[images] {route_info}")

    params = {"model": model, "prompt": data["prompt"]}
    for k in ("n", "size", "quality", "response_format", "style", "user", "background"):
        if k in data:
            params[k] = data[k]

    try:
        client = get_client(prov_cfg)
        resp = client.images.generate(**params)
        try:
            return jsonify(resp.model_dump())
        except Exception:
            return jsonify(resp)
    except Exception as e:
        return _map_error(e, "images")


# ===========================================================================
# Misc: health + model listing (some clients probe /models)
# ===========================================================================
@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "providers": sorted(PROVIDERS.keys())})


@app.route("/models", methods=["GET"])
@app.route("/v1/models", methods=["GET"])
def models():
    ids = set(MODEL_ROUTES.keys())
    if DEFAULT_MODEL:
        ids.add(DEFAULT_MODEL)
    data = [{"id": m, "object": "model", "created": int(time.time()), "owned_by": "affine-copilot-fix"}
            for m in sorted(ids)]
    return jsonify({"object": "list", "data": data})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")),
            debug=_as_bool(os.getenv("DEBUG", "true")))
