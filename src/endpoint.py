from flask import Flask, request, jsonify, Response, stream_with_context
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
import os
import time

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Settings
CREATE_LOG = bool(os.getenv('CREATE_LOG', False))
AI_PROVIDER = os.getenv('AI_PROVIDER', 'gemini')

# Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', '')

# OpenRouter
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', '')

# Log setup
LOG_PATH = "logs"
home_directory = os.path.dirname(__file__)
log_directory = os.path.join(home_directory, LOG_PATH)
os.makedirs(log_directory, exist_ok=True)

def is_chat_conversation(messages):
    user_messages = [m for m in messages if m['role'] == 'user']
    assistant_messages = [m for m in messages if m['role'] == 'assistant']
    return len(user_messages) > 1 or len(assistant_messages) > 0


def call_gemini(messages, model, system_instruction):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}'
    headers = {"Content-Type": "application/json"}

    history = []
    for msg in messages:
        role = "user" if msg['role'] == 'user' else "model"
        history.append({"role": role, "parts": [{"text": msg['content']}]})

    payload = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": [history]
    }

    resp = requests.post(url, headers=headers, json=payload)
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def call_openrouter(messages, model, system_instruction=None):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "stream": False
    }

    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def stream_openrouter(messages, model):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "stream": True
    }

    with requests.post(url, headers=headers, json=payload, stream=True) as resp:
        for line in resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                chunk = line.removeprefix("data: ").strip()
                if chunk == "[DONE]":
                    yield "data: [DONE]\n\n"
                    break
                try:
                    parsed = json.loads(chunk)
                    yield f"data: {json.dumps(parsed)}\n\n"
                except Exception as e:
                    print(f"Parse error: {e}")


def stream_openai_format(content):
    response_id = "chatcmpl-mocked"
    timestamp = int(time.time())
    for chunk in content.split():
        data = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": timestamp,
            "model": "gpt-4",
            "choices": [{
                "delta": {"content": chunk + " "},
                "index": 0,
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(data)}\n\n"
    yield "data: [DONE]\n\n"


def call_ai(messages, model, system_instruction=None):
    if AI_PROVIDER == 'gemini':
        return call_gemini(messages, model, system_instruction)
    elif AI_PROVIDER == 'openrouter':
        return call_openrouter(messages, model, system_instruction)
    else:
        raise ValueError(f"Unsupported AI_PROVIDER: {AI_PROVIDER}")


def stream_ai(messages, model, system_instruction=None):
    if AI_PROVIDER == 'gemini':
        content = call_gemini(messages, model, system_instruction)
        return stream_openai_format(content)
    elif AI_PROVIDER == 'openrouter':
        return stream_openrouter(messages, model)
    else:
        raise ValueError(f"Unsupported AI_PROVIDER: {AI_PROVIDER}")


@app.route('/chat/completions', methods=['POST'])
def chat_completions():
    try:
        data = request.json
        messages = data.get("messages", [])
        stream = data.get("stream", False)

        model = GEMINI_MODEL if AI_PROVIDER == 'gemini' else OPENROUTER_MODEL

        print(f"Model: {model}")
        print(f"AI_PROVIDER: {AI_PROVIDER}")

        if not messages:
            return jsonify({"error": "No messages provided"}), 400

        system_instruction = None
        if AI_PROVIDER == "gemini" and len(messages) >= 2:
            system_instruction = messages[0]['content']

        is_chat = is_chat_conversation(messages)
        print(f"Chat mode: {is_chat}")

        if CREATE_LOG:
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(os.path.join(log_directory, "chat_completions.log"), "a") as f:
                    f.write(f"\n=== {timestamp} ===\n")
                    f.write(f"\nModel: {model} \n")
                    f.write(f"\nProvider: {AI_PROVIDER}\n")
                    f.write(f"IP: {request.remote_addr}\n")
                    f.write(f"Chat mode: {is_chat}\n")
                    f.write(json.dumps(data, indent=2) + "\n")
            except Exception as e:
                print(f"Logging failed: {e}")

        if stream:
            return Response(
                stream_with_context(stream_ai(messages, model, system_instruction)),
                mimetype='text/event-stream'
            )
        else:
            content = call_ai(messages, model, system_instruction)
            return jsonify({
                "choices": [{"message": {"role": "assistant", "content": content}}]
            })

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
