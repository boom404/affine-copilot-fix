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