# GesahniV2
# 🦙✨ LLaMA-GPT Smart Assistant (with Home Assistant Integration)

Turn your crib into a smart castle with a slick, locally-powered AI assistant—leveraging LLaMA for smooth convos and GPT-4o for heavy-duty tasks. Seamlessly control your smart home via Home Assistant and keep interactions natural and context-aware. Ready to flex your smart-home hustle? Let's get it.

---

## 🛠️ Tech Stack

* **Local LLaMA 3** (via Ollama) for quick, local responses.
* **GPT-4o** for complex queries (code, research, multi-step logic).
* **FastAPI** backend for blazing-fast REST endpoints.
* **Home Assistant** for ultimate home automation.
* **Docker** for easy scalability and deployment.

## 🚀 Quick Start

### 📥 1. Setup Ollama & LLaMA 3

* Install Ollama CLI and pull LLaMA 3.

```bash
ollama pull llama3
ollama run llama3
```

### 🖥️ 2. Backend Installation

Clone the repo and install dependencies:

```bash
git clone <your-repo-url>
cd your-project
pip install -r requirements.txt
cp .env.example .env
```

### 🔑 3. Configure Environment

Update the copied `.env` with your credentials:

```env
OPENAI_API_KEY=your_openai_key
HOME_ASSISTANT_URL=http://your-ha-instance
HOME_ASSISTANT_TOKEN=your_long_lived_token
```

### 🌐 4. Launch Backend

Start FastAPI:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 📦 Docker Deploy

```bash
docker build -t smart-assistant .
docker run -d -p 8000:8000 --env-file .env smart-assistant
```

## 🎯 Endpoints

* `/ask`: Send your prompt here.
* `/health`: Check backend health.
* `/config`: View current config.
* `/intent-test`: Debug your prompt intent.

## 🤖 Smart Routing Logic

* **Home Assistant**: Automation and device commands.
* **LLaMA**: Casual conversation, quick info.
* **GPT-4o**: Complex questions, coding, deep research.

## 🧠 Advanced Features

* **Context-Aware Memory**: Remembers recent prompts.
* **Dynamic Entity Resolution**: Smartly matches your commands to HA entities.
* **Robust Fail-safes**: Seamless fallbacks (LLaMA → GPT, graceful HA errors).

## 📈 Future Enhancements

* Voice Activation (Porcupine/Vosk)
* Mobile App (React Native/PWA)
* Custom Skills (Calendar, Weather, Music)
* Advanced Notifications (Pushover/Shortcuts)
* Personality Modules (Customize assistant's tone)

---

### 🛟 Troubleshooting & Logs

* Check logs at `/config` endpoint.
* Detailed error logs saved locally.

---

Made by the King, for the King. Let's run it! 🚀🔥
