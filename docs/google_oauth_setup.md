# Google OAuth Setup Guide

This guide explains how to set up Google OAuth for user authentication in Gesahni.

## Overview

The application supports Google OAuth for user sign-in, allowing users to authenticate using their Google accounts. The implementation includes:

- Frontend Google sign-in button
- Backend OAuth flow handling
- Secure cookie-based token storage
- Integration with the existing authentication system

## Backend Configuration

### Environment Variables

Add the following environment variables to your `.env` file:

```bash
# Google OAuth Configuration
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/google/oauth/callback

# For production, update the redirect URI to your domain
# GOOGLE_REDIRECT_URI=https://yourdomain.com/google/oauth/callback
```

### Google Cloud Console Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google+ API and Google OAuth2 API
4. Go to "Credentials" → "Create Credentials" → "OAuth 2.0 Client IDs"
5. Configure the OAuth consent screen:
   - Add your application name and description
   - Add authorized domains
   - Add scopes: `openid`, `email`, `profile`
6. Create OAuth 2.0 Client ID:
   - Application type: Web application
   - Authorized redirect URIs: `http://127.0.0.1:8000/google/oauth/callback` (for development)
   - Copy the Client ID and Client Secret to your environment variables

## Frontend Implementation

### Components

- **GoogleSignInButton**: Reusable component for Google sign-in
- **Login Page**: Updated to include Google sign-in option

### Features

- **Dual OAuth Flow Support**: Handles both cookie-based and URL token-based OAuth redirects
- **Error Handling**: Displays OAuth errors to users
- **Loading States**: Shows loading indicators during OAuth flow
- **Responsive Design**: Works on desktop and mobile devices

## API Endpoints

### Backend Routes

- `GET /v1/google/auth/login_url` - Get Google OAuth URL
- `GET /v1/google/oauth/callback` - Handle OAuth callback
- `GET /v1/auth/google/start` - Alternative OAuth start endpoint
- `GET /v1/auth/google/callback` - Alternative OAuth callback endpoint

### Frontend API Functions

- `getGoogleAuthUrl(next?: string)` - Get OAuth URL from backend
- `initiateGoogleSignIn(next?: string)` - Start OAuth flow

## OAuth Flow

1. **User clicks "Continue with Google"** button
2. **Frontend calls** `/v1/google/auth/login_url` to get OAuth URL
3. **User is redirected** to Google OAuth consent screen
4. **Google redirects back** to `/v1/google/oauth/callback` with authorization code
5. **Backend exchanges** code for tokens and user info
6. **Backend sets** HttpOnly cookies with JWT tokens
7. **User is redirected** back to the application
8. **Frontend detects** cookies and completes authentication

## Security Features

- **HttpOnly Cookies**: Tokens stored in secure, HttpOnly cookies
- **PKCE Flow**: Uses PKCE (Proof Key for Code Exchange) for enhanced security
- **State Validation**: Validates OAuth state parameter to prevent CSRF attacks
- **Secure Redirects**: Validates redirect URLs to prevent open redirect attacks
- **Token Encryption**: Optional token encryption at rest

## Testing

### Frontend Tests

Run the Google OAuth tests:

```bash
cd frontend
npm test -- --testPathPattern="GoogleSignInButton|login.page.google"
```

### Backend Tests

Run the backend OAuth tests:

```bash
cd tests
python -m pytest test_google_oauth_login.py -v
```

## Troubleshooting

### Common Issues

1. **"google_oauth_unconfigured" error**
   - Check that `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set
   - Verify the redirect URI matches exactly

2. **"invalid_grant" error**
   - Authorization code has expired (codes are short-lived)
   - User needs to restart the OAuth flow

3. **"access_denied" error**
   - User cancelled the OAuth consent
   - Check OAuth consent screen configuration

4. **Redirect URI mismatch**
   - Ensure the redirect URI in Google Cloud Console matches your environment variable
   - For development: `http://127.0.0.1:8000/google/oauth/callback`
   - For production: `https://yourdomain.com/google/oauth/callback`

### Debug Mode

Enable debug logging by setting:

```bash
LOG_LEVEL=DEBUG
```

## Production Deployment

1. **Update Redirect URIs**: Change `GOOGLE_REDIRECT_URI` to your production domain
2. **Update OAuth Consent Screen**: Add your production domain to authorized domains
3. **Enable HTTPS**: Ensure your application uses HTTPS in production
4. **Review Scopes**: Only request necessary OAuth scopes
5. **Monitor Usage**: Check Google Cloud Console for OAuth usage metrics

## Integration with Existing Auth

The Google OAuth implementation integrates seamlessly with the existing authentication system:

- Uses the same JWT token format
- Compatible with existing session management
- Works with the auth orchestrator
- Supports the same user store and permissions
