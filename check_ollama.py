import requests
import json
import sys

OLLAMA_HOST = "http://localhost:11434"
TARGET_MODEL = "deepseek-r1:latest"

def check_ollama():
    print(f"--- Checking Ollama at {OLLAMA_HOST} ---")
    
    # 1. Check if server is up
    try:
        resp = requests.get(f"{OLLAMA_HOST}/", timeout=5)
        if resp.status_code == 200:
            print("✅ Ollama server is running.")
        else:
            print(f"⚠️ Ollama server responded with {resp.status_code}.")
    except Exception as e:
        print(f"❌ Could not connect to Ollama: {e}")
        return

    # 2. List models
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=10)
        data = resp.json()
        models = [m['name'] for m in data.get('models', [])]
        print(f"Available models: {models}")
        
        if TARGET_MODEL in models:
            print(f"✅ Target model '{TARGET_MODEL}' is available.")
        else:
            print(f"❌ Target model '{TARGET_MODEL}' is NOT found.")
            if models:
                print(f"👉 Suggest changing config to use '{models[0]}' or running `ollama pull {TARGET_MODEL}`")
    except Exception as e:
        print(f"❌ Error listing models: {e}")

if __name__ == "__main__":
    check_ollama()
