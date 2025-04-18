# Affine Copilot Fix

This python script creates a small http server, to handle the Affine Copilot feature with Gemini from Google. Gemini has a free-tier AI API feature.

## Create API Key

Get a free Gemini API Key https://aistudio.google.com/apikey

## Docker Installation

I'm using Affine in a docker container. You need to create `config.json` in your volumes and enable the copilot feature.  The baseUrl must be link to your script. "apiKey, can as it is. It has no effect.

```bash
nano ./volumes/affine/self-host/config/config.json 
```

Content on my config.json

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

I'musing two seperate networks. One between the containers `affine-net` and `treaefik-net` for the reverse proxy  

```yml

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
        - API_KEY=<ENTER YOUR FREE GEMINI API KEY>
        - AI_GEMINI_MODEL=gemini-2.0-flash
    ports:
        - 5000:5000
    image: affine-copilot-fix:latest
    networks:
        - traefik-net
        - affine-net
```

## Switch to source dir
    cd ./src


## Installation without Docker

Create .env file and change your settings

```
cp .env.example .env
```



## Create virtual environment

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
```bash
python endpoint.py
```
