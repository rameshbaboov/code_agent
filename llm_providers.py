import requests, os
def chat_once(cfg, messages):
    prov = cfg["provider"]["name"]
    if prov == "ollama":
        model = cfg["provider"]["model"]
        return _ollama_chat(model, messages, cfg["timeouts"]["llm"])
    elif prov == "openai":
        from openai import OpenAI
        client = OpenAI()
        model = cfg["provider"]["model"]
        resp = client.chat.completions.create(model=model, messages=messages, temperature=0.2)
        return resp.choices[0].message.content
    raise ValueError("Unknown provider")

def _ollama_chat(model, messages, timeout):
    r = requests.post("http://localhost:11434/api/chat",
                      json={"model": model, "messages": messages, "stream": False},
                      timeout=timeout)
    r.raise_for_status()
    return r.json()["message"]["content"]
