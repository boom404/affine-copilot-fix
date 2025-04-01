# Affine Copilot Fix

This python script creates a small http server, to handle the Affine Copilot feature with Gemini from Google. Gemini has a free-tier AI API feature.

## Enable Copilot in Affince

I'm using Affine in a docker container. You need to find "affine.js" in your volumes and enable the copilot feature. Please remove the comments to enable and add "baseURL". The baseURL must be link to your script. "apiKey, can as it is. It has no effect.

    sudo nano affine.js 
    ...
    // /* Copilot Plugin */
        AFFiNE.use('copilot', {
        openai: {
            baseURL: 'http://192.168.7.94:5000',
            apiKey: 'your-key',
        }
    //   fal: {
    //     apiKey: 'your-key',
    //   },
    //   unsplashKey: 'your-key',
    //   storage: {
    //     provider: 'cloudflare-r2',
    //     bucket: 'copilot',
    //   }
        })
    ...

## Switch to source dir
    cd ./src

## Create API Key
    cp .env.example .env

Get a free Gemini API Key https://aistudio.google.com/apikey

## Create virtual environment
    python -m venv myenv

## Activate it
### On Windows:
    myenv\Scripts\activate
### On Mac/Linux:
    source myenv/bin/activate

## Install requirements
    pip install -r requirements.txt

## Run your server
    python endpoint.py

