# 🚀 Gesahni Development Commands

## Quick Start Commands

| Command | Description |
|---------|-------------|
| `gs` | Start both backend and frontend |
| `gx` | Stop all development processes |
| `gr` | Restart both services |
| `gc` | Clear cookies and restart fresh |

## Individual Services

| Command | Description |
|---------|-------------|
| `gb` | Start only backend |
| `gf` | Start only frontend |

## Utilities

| Command | Description |
|---------|-------------|
| `gst` | Check if services are running |
| `gt` | Test localhost configuration |
| `go` | Open in browser |
| `gh` | Show this help |

## Navigation

| Command | Description |
|---------|-------------|
| `g` | Navigate to project directory |

## URLs

- **Frontend**: http://localhost:3000
- **Backend**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/healthz/ready

## Usage Examples

```bash
# Start everything
gs

# Check status
gst

# Open in browser
go

# Stop everything
gx

# Restart everything
gr

# Clear cookies and restart
gc

# Start only backend
gb

# Start only frontend
gf
```

## Notes

- All commands automatically navigate to the correct directory
- The `PORT` environment variable is automatically unset for frontend to prevent conflicts
- Backend runs on `localhost:8000`
- Frontend runs on `localhost:3000`
- All services use localhost consistently
