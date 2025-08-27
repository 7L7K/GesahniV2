# Version Update Checklist

## Pre-Release
- [ ] Run full test suite: `pytest`
- [ ] Check linting: `ruff check .`
- [ ] Update any version numbers in code/docs
- [ ] Review changelog/draft release notes
- [ ] Test critical user flows manually

## Release Steps
1. **Create and push version tag:**
   ```bash
   git tag -a v0.5.1 -m "Release v0.5.1: Security hardening and JWT improvements"
   git push origin v0.5.1
   ```

2. **Create GitHub Release** (if using GitHub):
   - Go to Releases tab
   - Click "Create a new release"
   - Select the new tag
   - Add release notes summarizing changes

3. **Update deployment** (if applicable):
   ```bash
   # Pull latest and restart services
   git pull origin main
   # Restart your services
   ```

## Post-Release
- [ ] Monitor logs for any new issues
- [ ] Update any documentation with new version
- [ ] Announce to users if applicable
