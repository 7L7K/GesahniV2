# Next.js Dev Server Configuration

## Requirements Status ✅

All requirements for the Next.js development server have been implemented:

### 1. Bind to :: (IPv6 and IPv4) ✅
- **Implementation**: `-H ::` flag in package.json scripts
- **Location**: `frontend/package.json` lines 5-6
- **Effect**: Server accepts connections on both IPv6 and IPv4 interfaces

### 2. Prefer IPv4 Resolution ✅
- **Implementation**: `--dns-result-order=ipv4first` in NODE_OPTIONS
- **Location**: `frontend/package.json` lines 5-6 and `scripts/dev.sh` line 33
- **Effect**: Browsers and Node.js will resolve localhost to 127.0.0.1 (IPv4) instead of ::1 (IPv6)

### 3. Access via localhost:3000 ✅
- **Implementation**: All environment variables configured to use `http://localhost:3000`
- **Locations**:
  - `frontend/package.json` - All Clerk and site URL environment variables
  - `scripts/dev.sh` - Consistent environment variable configuration
  - `env.example` - CORS_ALLOW_ORIGINS set to localhost:3000
  - `frontend/next.config.js` - Asset prefix fallback to localhost:3000

## Configuration Details

### Package.json Scripts
```json
{
  "dev": "NODE_OPTIONS=\"--dns-result-order=ipv4first --max-old-space-size=4096\" NEXT_PUBLIC_SITE_URL=http://localhost:3000 CLERK_SIGN_IN_URL=http://localhost:3000/sign-in CLERK_SIGN_UP_URL=http://localhost:3000/sign-up CLERK_AFTER_SIGN_IN_URL=http://localhost:3000 CLERK_AFTER_SIGN_UP_URL=http://localhost:3000 next dev -H ::",
  "dev:turbo": "NODE_OPTIONS=\"--dns-result-order=ipv4first --max-old-space-size=4096\" NEXT_PUBLIC_SITE_URL=http://localhost:3000 CLERK_SIGN_IN_URL=http://localhost:3000/sign-in CLERK_SIGN_UP_URL=http://localhost:3000/sign-up CLERK_AFTER_SIGN_IN_URL=http://localhost:3000 CLERK_AFTER_SIGN_UP_URL=http://localhost:3000 next dev --turbopack -H ::"
}
```

### Development Script
The `scripts/dev.sh` script has been updated to include the same environment variables for consistency when using `pnpm dev`.

## Benefits

1. **Universal Compatibility**: The `-H ::` binding ensures the server works on all network configurations
2. **Predictable Resolution**: IPv4-first DNS resolution prevents browsers from accidentally using IPv6 localhost
3. **Consistent Access**: All bookmarks, scripts, SDKs, and configs can reliably use `http://localhost:3000`
4. **Development Consistency**: Both direct `npm run dev` and `scripts/dev.sh` use identical configurations

## Testing

To verify the configuration:

1. **IPv6/IPv4 Binding**: The server should be accessible via both `http://localhost:3000` and `http://[::1]:3000`
2. **IPv4 Preference**: DNS resolution should prefer 127.0.0.1 over ::1
3. **Consistent Access**: All internal references use `http://localhost:3000`

## Environment Variables

The following environment variables are consistently set to use localhost:3000:
- `NEXT_PUBLIC_SITE_URL`
- `CLERK_SIGN_IN_URL`
- `CLERK_SIGN_UP_URL`
- `CLERK_AFTER_SIGN_IN_URL`
- `CLERK_AFTER_SIGN_UP_URL`
- `CORS_ALLOW_ORIGINS` (backend)

This ensures that all authentication flows, CORS policies, and internal redirects work correctly with the localhost:3000 URL.
