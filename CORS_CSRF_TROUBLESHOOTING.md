# CORS/CSRF Troubleshooting Guide

## Issue Summary
The frontend can talk to the backend at first, but auth requests are being blocked due to CORS/CSRF configuration mismatches.

## ✅ Fixed Issues

### 1. Missing CORS_ALLOW_CREDENTIALS Environment Variable
**Problem**: The `CORS_ALLOW_CREDENTIALS` environment variable was not explicitly set in `.env`.

**Solution**: Added `CORS_ALLOW_CREDENTIALS=true` to the `.env` file.

**Verification**:
```bash
grep CORS_ALLOW_CREDENTIALS .env
# Should show: CORS_ALLOW_CREDENTIALS=true
```

### 2. Verified Backend Configuration
**Status**: ✅ All backend configurations are correct

- **CORS Origins**: `http://localhost:3000` (correct)
- **CORS Credentials**: `true` (correct)
- **CSRF Protection**: Disabled by default (correct for development)
- **Authentication Endpoints**: Working correctly

### 3. Verified Frontend Configuration
**Status**: ✅ All frontend configurations are correct

- **Authentication Mode**: Cookie-based (`NEXT_PUBLIC_HEADER_AUTH_MODE=0`)
- **API Endpoints**: Correct (`/v1/login`, `/v1/register`, `/v1/whoami`)
- **CORS Headers**: Properly configured

## 🔍 Diagnostic Results

All authentication flow tests pass:
- ✅ CORS Preflight: PASS
- ✅ Whoami Endpoint: PASS
- ✅ Login Endpoint: PASS
- ✅ Frontend Health: PASS

## 🚨 If Issues Persist

### 1. Browser-Specific Issues

**Check Browser Console**:
1. Open Developer Tools (F12)
2. Go to Console tab
3. Look for CORS errors or authentication failures
4. Check for JavaScript errors

**Check Network Tab**:
1. Go to Network tab in Developer Tools
2. Try to login/authenticate
3. Look for failed requests (red entries)
4. Check request/response headers

**Check Application Tab**:
1. Go to Application tab in Developer Tools
2. Check Cookies section
3. Verify `access_token` and `refresh_token` cookies are present
4. Check cookie domain and path settings

### 2. Browser Security Settings

**Chrome/Edge**:
1. Go to `chrome://settings/content/cookies`
2. Ensure "Allow all cookies" or "Block third-party cookies" is not blocking localhost
3. Check if "Block third-party cookies" is enabled

**Firefox**:
1. Go to `about:preferences#privacy`
2. Check cookie settings
3. Ensure localhost cookies are not blocked

**Safari**:
1. Go to Safari > Preferences > Privacy
2. Check cookie settings
3. Ensure localhost is not blocked

### 3. Development Environment Issues

**Check Port Conflicts**:
```bash
# Check if ports are in use
lsof -i :3000
lsof -i :8000
```

**Check Environment Variables**:
```bash
# Backend
grep -E "(CORS_ALLOW|CSRF_ENABLED)" .env

# Frontend
grep -E "(NEXT_PUBLIC_API_ORIGIN|NEXT_PUBLIC_HEADER_AUTH_MODE)" frontend/.env*
```

**Restart Services**:
```bash
# Restart backend
pkill -f "python.*main.py"
python app/main.py

# Restart frontend
cd frontend
npm run dev
```

### 4. Network/Proxy Issues

**Check for Proxy Settings**:
- Ensure no proxy is interfering with localhost requests
- Check if corporate firewall is blocking localhost

**Check Hosts File**:
```bash
# Check if localhost is properly configured
cat /etc/hosts | grep localhost
```

### 5. Advanced Debugging

**Run Diagnostic Script**:
```bash
node debug_auth_flow.js
```

**Test with curl**:
```bash
# Test CORS preflight
curl -v -H "Origin: http://localhost:3000" \
     -H "Access-Control-Request-Method: GET" \
     -H "Access-Control-Request-Headers: content-type" \
     -X OPTIONS http://localhost:8000/v1/whoami

# Test login
curl -v -H "Origin: http://localhost:3000" \
     -H "Content-Type: application/json" \
     -d '{"username":"testuser","password":"testpass123"}' \
     http://localhost:8000/v1/login

# Test whoami with cookies
curl -v -H "Origin: http://localhost:3000" \
     -b cookies.txt \
     http://localhost:8000/v1/whoami
```

## 📋 Configuration Checklist

### Backend (.env)
- [ ] `CORS_ALLOW_ORIGINS=http://localhost:3000`
- [ ] `CORS_ALLOW_CREDENTIALS=true`
- [ ] `CSRF_ENABLED=0` (for development)
- [ ] `JWT_SECRET=change-me` (or your secret)

### Frontend (frontend/.env.local)
- [ ] `NEXT_PUBLIC_API_ORIGIN=http://localhost:8000`
- [ ] `NEXT_PUBLIC_HEADER_AUTH_MODE=0`

### Browser
- [ ] No CORS errors in console
- [ ] Cookies are being set and sent
- [ ] Network requests are successful
- [ ] No security policies blocking localhost

## 🆘 Still Having Issues?

If you're still experiencing CORS/CSRF issues after following this guide:

1. **Check the logs**: Look at backend console output for errors
2. **Browser compatibility**: Try a different browser
3. **Incognito mode**: Test in incognito/private browsing mode
4. **Clear browser data**: Clear cookies and cache
5. **Network inspection**: Use browser dev tools to inspect failed requests

## 📞 Support

If issues persist, please provide:
1. Browser console errors
2. Network tab failed requests
3. Backend logs
4. Environment configuration
5. Steps to reproduce the issue
