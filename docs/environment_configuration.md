# Environment Configuration

This document explains the environment configuration system for GesahniV2, which has been designed to eliminate configuration drift and provide clear separation between different deployment environments.

## Overview

The environment configuration system consists of:

1. **`env.template`** - Base template with all available configuration options
2. **`env.dev`** - Development environment configuration
3. **`env.staging`** - Staging environment configuration  
4. **`env.prod`** - Production environment configuration
5. **`scripts/switch_env.sh`** - Script to easily switch between environments

## Environment-Specific Configuration

Each environment file defines the following key variables that change between environments:

### Frontend and Backend URLs
- `APP_URL` - Frontend base URL
- `API_URL` - Backend base URL

### CORS Configuration
- `CORS_ALLOW_ORIGINS` - Frontend origins allowed by backend

### Cookie Security
- `COOKIE_SECURE` - Whether cookies require HTTPS (0=no, 1=yes)
- `COOKIE_SAMESITE` - SameSite cookie policy (lax, strict, none)

**⚠️ CRITICAL SECURITY WARNING ⚠️**: If you set `COOKIE_SAMESITE=none` to allow cross-site cookies, you **MUST** also set `COOKIE_SECURE=1` or modern browsers will reject the cookies. This requires HTTPS in production.

### Authentication Mode
- `NEXT_PUBLIC_HEADER_AUTH_MODE` - Authentication mode (0=cookie, 1=header)

## Environment Configurations

### Development (`env.dev`)
- **URLs**: `http://localhost:3000` (frontend), `http://localhost:8000` (backend)
- **CORS**: `http://localhost:3000`
- **Cookies**: `COOKIE_SECURE=0`, `COOKIE_SAMESITE=lax`
- **Security**: Relaxed for local development
- **DEV_MODE**: `1` (enables development features)

### Staging (`env.staging`)
- **URLs**: `https://staging.gesahni.com` (frontend), `https://api-staging.gesahni.com` (backend)
- **CORS**: `https://staging.gesahni.com`
- **Cookies**: `COOKIE_SECURE=1`, `COOKIE_SAMESITE=lax`
- **Security**: Production-like but with some flexibility
- **DEV_MODE**: `0`

### Production (`env.prod`)
- **URLs**: `https://app.gesahni.com` (frontend), `https://api.gesahni.com` (backend)
- **CORS**: `https://app.gesahni.com`
- **Cookies**: `COOKIE_SECURE=1`, `COOKIE_SAMESITE=strict`
- **Security**: Maximum security settings
- **DEV_MODE**: `0`

## Usage

### Switching Environments

Use the provided script to switch between environments:

```bash
# Switch to development environment
./scripts/switch_env.sh dev

# Switch to staging environment
./scripts/switch_env.sh staging

# Switch to production environment
./scripts/switch_env.sh prod
```

The script will:
1. Backup your current `.env` file (if it exists)
2. Copy the appropriate environment file to `.env`
3. Display the key configuration differences
4. Remind you to set required secrets and API keys

### Manual Setup

If you prefer to set up environments manually:

1. Copy the appropriate environment file to `.env`:
   ```bash
   cp env.dev .env      # For development
   cp env.staging .env  # For staging
   cp env.prod .env     # For production
   ```

2. Edit `.env` to add your specific configuration:
   - API keys and secrets
   - Database connection strings
   - JWT secrets
   - Update URLs to match your actual deployment

### Environment Loading Precedence

The environment loading system follows this precedence (highest to lowest):

1. `.env` - Overrides existing process environment values
2. `env.example` - Fills missing keys only (never overrides)
3. `env.dev` - Fills missing keys only
4. `env.staging` - Fills missing keys only
5. `env.prod` - Fills missing keys only

This means that `.env` always takes precedence, but the environment-specific files provide sensible defaults for missing values.

## Frontend Configuration

For the frontend, you'll need to set the corresponding `NEXT_PUBLIC_` environment variables. The backend environment files include these, but you may need to set them separately in your frontend deployment:

```bash
# Development
NEXT_PUBLIC_API_ORIGIN=http://localhost:8000
NEXT_PUBLIC_HEADER_AUTH_MODE=0

# Staging
NEXT_PUBLIC_API_ORIGIN=https://api-staging.gesahni.com
NEXT_PUBLIC_HEADER_AUTH_MODE=0

# Production
NEXT_PUBLIC_API_ORIGIN=https://api.gesahni.com
NEXT_PUBLIC_HEADER_AUTH_MODE=0
```

## Security Considerations

### Development
- Uses HTTP for local development
- Relaxed cookie security
- Allows localhost CORS

### Staging
- Uses HTTPS
- Secure cookies enabled
- Production-like security with some flexibility

### Production
- Uses HTTPS
- Maximum cookie security (Secure + SameSite=strict)
- Strict CORS policy
- No development features enabled

## Migration from Old Configuration

If you're migrating from the old configuration system:

1. **Backup your current `.env`**:
   ```bash
   cp .env .env.backup.$(date +%Y%m%d_%H%M%%S)
   ```

2. **Switch to your target environment**:
   ```bash
   ./scripts/switch_env.sh dev  # or staging/prod
   ```

3. **Copy your secrets and API keys** from the backup to the new `.env`

4. **Update URLs** to match your actual deployment

5. **Test the configuration** to ensure everything works correctly

## Troubleshooting

### Common Issues

1. **CORS errors**: Ensure `CORS_ALLOW_ORIGINS` matches your frontend URL exactly
2. **Cookie issues**: Check `COOKIE_SECURE` and `COOKIE_SAMESITE` settings
3. **Authentication problems**: Verify `NEXT_PUBLIC_HEADER_AUTH_MODE` is consistent between frontend and backend

### Debugging

To see which environment files are being loaded:

```bash
# Check the logs when starting the application
# Look for lines like:
# env_loader: applied .env=X (override), .env.example filled=Y, dev filled=Z, ...
```

### Environment File Validation

You can validate your environment files using:

```bash
# Check for syntax errors
grep -v '^#' env.dev | grep -v '^$' | while read line; do
  if [[ $line =~ ^[A-Z_]+=.*$ ]]; then
    echo "✓ $line"
  else
    echo "✗ Invalid format: $line"
  fi
done
```

## Best Practices

1. **Never commit `.env` files** - They contain secrets
2. **Use the switch script** - It provides safety checks and backups
3. **Keep environment files in sync** - Update all environments when adding new variables
4. **Test all environments** - Ensure configurations work in each environment
5. **Document customizations** - Note any environment-specific customizations
6. **Use strong secrets** - Generate unique JWT secrets for each environment
7. **Regular backups** - Keep backups of your `.env` files

## Adding New Environment Variables

When adding new environment variables:

1. **Add to `env.template`** - Document the variable with a comment
2. **Add to all environment files** - Set appropriate values for each environment
3. **Update this documentation** - Document the new variable and its purpose
4. **Test in all environments** - Ensure the variable works correctly

Example:
```bash
# Add to env.template
NEW_FEATURE_ENABLED=0

# Add to env.dev
NEW_FEATURE_ENABLED=1

# Add to env.staging
NEW_FEATURE_ENABLED=1

# Add to env.prod
NEW_FEATURE_ENABLED=0
```
