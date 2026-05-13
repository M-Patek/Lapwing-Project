# Deployment Guide

## Local Deployment

### Prerequisites

- Python 3.11+
- DeepSeek API key

### Setup

1. **Clone repository**
```bash
git clone <repo-url>
cd Lapwing-Project
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your DeepSeek API key
```

5. **Run security check**
```bash
python security_check.py
```

6. **Start server**
```bash
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

## Docker Deployment

### Using Docker Compose

1. **Create .env file**
```bash
cp .env.example .env
# Edit .env
```

2. **Build and run**
```bash
docker-compose up --build -d
```

3. **View logs**
```bash
docker-compose logs -f lapwing
```

4. **Stop**
```bash
docker-compose down
```

### Using Docker

```bash
# Build
docker build -t lapwing .

# Run
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/json:/app/json \
  -v $(pwd)/logs:/app/logs \
  --name lapwing \
  lapwing
```

## Production Deployment

### Cloud Platforms

#### Railway
```bash
railway login
railway init
railway up
```

#### Heroku
```bash
heroku create lapwing-app
heroku config:set DEEPSEEK_API_KEY=your-key
git push heroku main
```

#### Fly.io
```bash
fly launch
fly deploy
```

### VPS Deployment

1. **SSH to server**
```bash
ssh user@your-server
```

2. **Clone and setup**
```bash
git clone <repo-url>
cd Lapwing-Project
```

3. **Run with Docker**
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Health Checks

- **API Health**: `GET http://localhost:8000/health`
- **WebSocket**: `ws://localhost:8000/ws`

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DEEPSEEK_API_KEY` | Yes | DeepSeek API key |
| `DEEPSEEK_BASE_URL` | No | Default: https://api.deepseek.com |
| `CHAT_MODEL` | No | Default: deepseek-v4-flash |
| `SCENE_MODEL` | No | Default: deepseek-v4-flash |
| `TEMPERATURE` | No | Default: 0.95 |
| `MAX_TOKENS` | No | Default: 4096 |

## Monitoring

View logs:
```bash
# Docker
docker-compose logs -f

# Local
tail -f logs/lapwing.log
```

## Backup

Backup data:
```bash
tar -czvf backup-$(date +%Y%m%d).tar.gz json/ logs/
```

Restore:
```bash
tar -xzvf backup-20240101.tar.gz
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| ImportError | Check `pip install -r requirements.txt` |
| API 503 | Check `.env` configuration |
| FAISS error | Install faiss-cpu: `pip install faiss-cpu` |
| Port in use | Change port: `--port 8001` |

## Security

- Never commit `.env` file
- Rotate API keys regularly
- Use HTTPS in production
- Enable firewall rules
