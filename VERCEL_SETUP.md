# Vercel + ngrok Setup Guide

## Current Status
- ✅ Backend running on: http://127.0.0.1:8000
- ✅ Frontend running on: http://localhost:5173  
- ✅ ngrok tunnel: https://94a5b0645561.ngrok-free.app
- ✅ CORS configured for ngrok and Vercel domains

## Vercel Environment Variables

Set these in your Vercel project settings:

```bash
VITE_API_URL=https://94a5b0645561.ngrok-free.app
```

**Note:** The ngrok URL will change when you restart ngrok. For a permanent solution, consider ngrok's paid plan with custom domains.

## Backend CORS Configuration

The backend is already configured to accept requests from:
- `http://localhost:5173` (local development)
- `https://94a5b0645561.ngrok-free.app` (current ngrok URL)
- Any `*.vercel.app` domain (via regex)
- Any `*.ngrok-free.app` domain (via regex)

## API Headers for ngrok

When calling the API through ngrok, include this header to skip the browser warning:
```javascript
headers: {
  'ngrok-skip-browser-warning': 'true'
}
```

## Commands to Keep Running

### Backend
```powershell
cd "c:\Users\micha\Documents\projects\tod\Truck Planner\TP 3 9.7.25\backend"
$env:PYTHONPATH = "${PWD}"
& "C:/Users/micha/Documents/projects/tod/Truck Planner/TP 3 9.7.25/.venv/Scripts/python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### ngrok (if you need to restart)
```powershell
& "$env:USERPROFILE\ngrok.exe" http 8000 --host-header=rewrite
```

### Frontend (local)
```powershell
cd "c:\Users\micha\Documents\projects\tod\Truck Planner\TP 3 9.7.25\frontend"
npm run dev
```

## Testing

- Local API: http://127.0.0.1:8000/health
- ngrok API: https://94a5b0645561.ngrok-free.app/health
- Local Frontend: http://localhost:5173
- Vercel Frontend: (deploy with VITE_API_URL set to ngrok URL)

## Next Steps

1. Deploy frontend to Vercel with `VITE_API_URL=https://94a5b0645561.ngrok-free.app`
2. Keep backend + ngrok running locally
3. Test the full flow: Vercel frontend → ngrok → local backend
4. For production: Set up AWS infrastructure or use a cloud backend service
