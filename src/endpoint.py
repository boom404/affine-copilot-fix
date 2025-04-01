from flask import Flask, request, jsonify, Response
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
import os

# Load the .env file
load_dotenv()

app = Flask(__name__)

#Settings
CREATE_LOG=bool(os.getenv('CREATE_LOG'))
API_KEY = os.getenv('API_KEY')
AI_GEMINI_MODEL = os.getenv('AI_GEMINI_MODEL')
LOG_PATH = "logs"

# Create the logs directory if it doesn't exist
home_directory = os.path.dirname(__file__) # directory of script
log_directory = os.path.join(home_directory, LOG_PATH)
#if not os.path.exists(log_directory):
#    os.makedirs(log_directory)

# Check if the environment variables are set
if not API_KEY:
    raise ValueError("API_KEY must be set in the environment variables.")

if not AI_GEMINI_MODEL:
    raise ValueError("AI_GEMINI_MODEL must be set in the environment variables.")

def handle_chat_request(messages, system_instruction):
    print("start handle_chat_request call")
    user_messages = [msg['content'] for msg in messages if msg['role'] == 'user' and msg['content']]
    last_user_message = user_messages[-1] if user_messages else ""
    
    text_response = do_api_call(last_user_message, system_instruction)

    return text_response

def format_response(content, stream=False):
    print("start format_response call")
    if stream:
        def generate():
            yield f"data: {json.dumps({'choices': [{'delta': {'content': content}}]})}\n\n"
            yield "data: [DONE]\n\n"
        return Response(generate(), mimetype='text/event-stream')
    else:
        return jsonify({
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": content
                }
            }]
        })
    
def do_api_call(text, system_instruction):
    print("start do_api_call call")
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{AI_GEMINI_MODEL}:generateContent?key={API_KEY}'
    headers = {"Content-Type": "application/json"}

    # The payload (data) to be sent in the request
    payload = {
        "contents": [{
            "parts": [{
                "text": text
            }]
        }],
        "system_instruction": {
            "parts": [{
                "text": system_instruction
            }]
        }
    }

    response = requests.post(url, headers=headers, data=json.dumps(payload))
    response_data = response.json()
    text_response = response_data["candidates"][0]["content"]["parts"][0]["text"]

    if(CREATE_LOG):
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Save to file for later inspection
            print(f"{log_directory}/ai_response.log")
            with open(f"{log_directory}/ai_response.log", "a") as log_file:
                log_file.write(f"\n=== {timestamp} ===\n")
                log_file.write(f"Instruction: {system_instruction}\n")
                log_file.write(f"Response: {text_response}\n")
                log_file.write(json.dumps(response_data, indent=2) + "\n")

        except Exception as e:
            print(e)
            # for any exception to be catched
            print(type(e))
            # to know the type of exception.

    return text_response    

def single_response(text, system_instruction):
    print("start single_response call")
    text_response = do_api_call(text, system_instruction)

    return text_response

@app.route('/chat/completions', methods=['POST'])
def chat_completions():
    try:
        data = request.json
        text_response = ""
        system_instruction = data['messages'][0]['content']
        user_content = data['messages'][1]['content']
        stream = data.get('stream', False)


        if(CREATE_LOG):
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Save to file for later inspection
                print(f"{log_directory}/post_requests.log")
                with open(f"{log_directory}/post_requests.log", "a") as log_file:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    client_ip = request.remote_addr
                    log_file.write(f"\n=== {timestamp} ===\n")
                    log_file.write(f"IP: {client_ip}\n")
                    log_file.write(json.dumps(data, indent=2) + "\n")

            except Exception as e:
                print(e)
                # for any exception to be catched
                print(type(e))
                # to know the type of exception.

        # Check if the messages is more than 2 (then it is a chat)
        if(len(data['messages']) > 2):
            text_response = handle_chat_request(data['messages'], system_instruction)        
        elif isinstance(user_content, list):
            text = user_content[0]["text"]
            text_response = single_response(text.strip(), system_instruction)

        # Check if text_response is not empty
        if(text_response):
            return format_response(text_response, stream)

        # Fallback
        return jsonify({"error": "Unsupported request"}), 400
          
    except Exception as e:
        print(e)
        # for any exception to be catched
        print(type(e))
        # to know the type of exception.        
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)