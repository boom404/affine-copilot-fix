from flask import Flask, request, jsonify
import json
from datetime import datetime

app = Flask(__name__)

def extract_user_content(messages):
    """Extract text content from user role messages"""
    user_contents = []
    for msg in messages:
        if msg.get('role') == 'user':
            content = msg.get('content')
            if isinstance(content, list):
                for item in content:
                    if item.get('type') == 'text':
                        user_contents.append(item.get('text'))
            elif isinstance(content, str):
                user_contents.append(content)
    return user_contents

@app.route('/', defaults={'path': ''}, methods=['POST'])
@app.route('/<path:path>', methods=['POST'])
def catch_all(path):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    client_ip = request.remote_addr
    
    try:
        json_data = request.get_json(force=True)
        data_type = "valid JSON"
        
        # Extract user messages if they exist
        user_texts = []
        if 'messages' in json_data:
            user_texts = extract_user_content(json_data['messages'])
        
    except Exception as e:
        json_data = {"raw_data": request.data.decode('utf-8')}
        data_type = f"invalid JSON ({str(e)})"
        user_texts = []
    
    # Print debug information
    print(f"\n=== Received POST at {timestamp} ===")
    print(f"Path: /{path}")
    print(f"From IP: {client_ip}")
    print(f"Content-Type: {request.headers.get('Content-Type')}")
    print(f"Data Type: {data_type}")
    
    if user_texts:
        print("\nUser Content Found:")
        for i, text in enumerate(user_texts, 1):
            print(f"{i}. {text}")
    
    print("\nFull Body Content:")
    print(json.dumps(json_data, indent=2))
    
  # Save to file for later inspection
    with open("post_requests.log", "a") as log_file:
        log_file.write(f"\n=== {timestamp} ===\n")
        log_file.write(f"Path: /{path}\n")
        log_file.write(f"IP: {client_ip}\n")
        log_file.write(json.dumps(json_data, indent=2) + "\n")

    return jsonify({
        "status": "success",
        "path": path,
        "user_content": user_texts,
        "full_data": json_data
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)