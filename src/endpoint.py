from flask import Flask, request, jsonify, Response, stream_with_context
import json
from datetime import datetime
from dotenv import load_dotenv
import os
import time
import openai
import logging

# Load environment variables
load_dotenv()
app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Settings
CREATE_LOG = bool(os.getenv('CREATE_LOG', False))

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')  # Required, even for OpenRouter
OPENAI_BASE_URL = os.getenv('OPENAI_BASE_URL', '')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', '')

# Log setup
LOG_PATH = "logs"
home_directory = os.path.dirname(__file__)
log_directory = os.path.join(home_directory, LOG_PATH)
os.makedirs(log_directory, exist_ok=True)

def get_openai_client(base_url=None):
    """
    Creates an OpenAI client with the specified base URL.
    If no base_url is set, it uses OpenAI's default.
    """
    if base_url:
        return openai.OpenAI(api_key=OPENAI_API_KEY, base_url=base_url)
    else:
        return openai.OpenAI(api_key=OPENAI_API_KEY)


def call_ai(messages, model):
    """Calls the AI model using the OpenAI library."""
    try:
        client = get_openai_client(OPENAI_BASE_URL)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
        )
        return response.choices[0].message.content
    except openai.APIConnectionError as e:
        raise Exception(f"Failed to connect to API: {e}")
    except openai.RateLimitError as e:
        raise Exception(f"API request exceeded rate limit: {e}")
    except openai.APIStatusError as e:
        raise Exception(f"API returned an API Status Error: {e}")
    except Exception as e:
        raise Exception(f"An unexpected error occurred: {e}")


def stream_ai(messages, model):
    """Streams the AI model response using the OpenAI library."""
    try:
        client = get_openai_client(OPENAI_BASE_URL)
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                data = {
                    "choices": [
                        {
                            "delta": {"content": chunk.choices[0].delta.content},
                            "index": 0,
                            "finish_reason": chunk.choices[0].finish_reason,
                        }
                    ]
                }
                yield f"data: {json.dumps(data)}\n\n"

        yield "data: [DONE]\n\n"    

    except openai.APIConnectionError as e:
        yield f"data: {json.dumps({'error': f'Failed to connect to API: {e}'})}\n\n"
        yield "data: [DONE]\n\n"
    except openai.RateLimitError as e:
        yield f"data: {json.dumps({'error': f'API request exceeded rate limit: {e}'})}\n\n"
        yield "data: [DONE]\n\n"
    except openai.APIStatusError as e:
        yield f"data: {json.dumps({'error': f'API returned an API Status Error: {e}'})}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': f'An unexpected error occurred: {e}'})}\n\n"

@app.route('/chat/completions', methods=['POST'])
def chat_completions():
    try:
        data = request.json
        messages = data.get("messages", [])
        stream = data.get("stream", False)

        if not messages:
            return jsonify({"error": "No messages provided"}), 400

        if CREATE_LOG:
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(os.path.join(log_directory, "chat_completions.log"), "a") as f:
                    f.write(f"\n=== {timestamp} ===\n")
                    f.write(f"\nModel: {OPENAI_MODEL} \n")
                    f.write(f"\nBaseUrl: {OPENAI_BASE_URL}\n")
                    f.write(f"\nIP: {request.remote_addr}\n")
                    f.write(json.dumps(data, indent=2) + "\n")
            except Exception as e:
                print(f"Logging failed: {e}")

        if stream:
            return Response(
                stream_with_context(stream_ai(messages, OPENAI_MODEL)),
                mimetype='text/event-stream'
            )
        else:
            content = call_ai(messages, OPENAI_MODEL)
            return jsonify({
                "choices": [{"message": {"role": "assistant", "content": content}}]
            })

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)