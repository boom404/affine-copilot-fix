from flask import Flask, request, jsonify, Response, stream_with_context
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
import os
import time

# Load the .env file
load_dotenv()

app = Flask(__name__)

# Settings
CREATE_LOG = bool(os.getenv('CREATE_LOG'))
API_KEY = os.getenv('API_KEY')
AI_GEMINI_MODEL = os.getenv('AI_GEMINI_MODEL')
LOG_PATH = "logs"

# Create the logs directory if it doesn't exist
home_directory = os.path.dirname(__file__)
log_directory = os.path.join(home_directory, LOG_PATH)
#os.makedirs(log_directory, exist_ok=True)

# Check if the environment variables are set
if not API_KEY:
    raise ValueError("API_KEY must be set in the environment variables.")

if not AI_GEMINI_MODEL:
    raise ValueError("AI_GEMINI_MODEL must be set in the environment variables.")

def handle_chat_request(messages, system_instruction):
    history = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        history.append({"role": role, "parts": [{"text": msg["content"]}]})
    return do_api_call(history, system_instruction)

def single_response(text, system_instruction):
    return do_api_call([{"role": "user", "parts": [{"text": text}]}], system_instruction)

def do_api_call(contents, system_instruction):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{AI_GEMINI_MODEL}:generateContent?key={API_KEY}'
    headers = {"Content-Type": "application/json"}

    payload = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": contents
    }

    response = requests.post(url, headers=headers, json=payload)
    response_data = response.json()

    if "candidates" not in response_data:
        raise Exception(f"Invalid Gemini response: {response_data}")

    text_response = response_data["candidates"][0]["content"]["parts"][0]["text"]

    if CREATE_LOG:
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(os.path.join(log_directory, "ai_response.log"), "a") as log_file:
                log_file.write(f"\n=== {timestamp} ===\n")
                log_file.write(f"Instruction: {system_instruction}\n")
                log_file.write(f"Response: {text_response}\n")
                log_file.write(json.dumps(response_data, indent=2) + "\n")
        except Exception as e:
            print(f"Logging failed: {e}")

    return text_response

def stream_openai_format(gemini_text, model="gpt-4"):
    response_id = "chatcmpl-mocked"
    timestamp = int(time.time())
    for chunk in gemini_text.split():
        data = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": timestamp,
            "model": model,
            "choices": [{
                "delta": {"content": chunk + " "},
                "index": 0,
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(data)}\n\n"
        #time.sleep(0.03)
    yield "data: [DONE]\n\n"

@app.route('/chat/completions', methods=['POST'])
def chat_completions():
    try:
        data = request.json
        stream = data.get("stream", False)
        messages = data.get("messages", [])
        if not messages or len(messages) < 2:
            return jsonify({"error": "Insufficient messages"}), 400

        system_instruction = messages[0]["content"]
        if CREATE_LOG:
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(os.path.join(log_directory, "post_requests.log"), "a") as log_file:
                    log_file.write(f"\n=== {timestamp} ===\n")
                    log_file.write(f"IP: {request.remote_addr}\n")
                    log_file.write(json.dumps(data, indent=2) + "\n")
            except Exception as e:
                print(f"Logging failed: {e}")

        if len(messages) > 2:
            response_text = handle_chat_request(messages, system_instruction)
        else:
            user_content = messages[1]["content"]
            response_text = single_response(user_content.strip(), system_instruction)

        if stream:
            return Response(
                stream_with_context(stream_openai_format(response_text)),
                mimetype="text/event-stream"
            )
        else:
            return jsonify({
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": response_text
                    }
                }]
            })

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
