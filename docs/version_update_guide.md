# Version Update Guide for GesahniV2

## Current Release Cadence
- **Current**: v0.5.0 (Aug 20, 2025)
- **Previous**: v0.2.0 (Aug 14, 2025)
- **Commits since last release**: 13

## Recommended Release Frequency

### Patch Releases (v0.5.1, v0.5.2, etc.)
- **When**: Every 1-2 weeks
- **What**: Bug fixes, security improvements, small features
- **Current candidates**: Security hardening, JWT improvements

### Minor Releases (v0.6.0, v0.7.0, etc.)
- **When**: Every 4-6 weeks
- **What**: New features, API changes, moderate refactors

### Major Releases (v1.0.0, v2.0.0, etc.)
- **When**: When core architecture changes significantly
- **What**: Breaking changes, complete rewrites, major milestones

## Quick Release Process

### For Patch Release:
```bash
# 1. Ensure you're on main branch with latest changes
git checkout main && git pull origin main

# 2. Run tests and checks
pytest -q
ruff check .

# 3. Create and push tag
git tag -a v0.5.1 -m "Release v0.5.1: Security hardening and JWT improvements"
git push origin v0.5.1

# 4. Create GitHub release (optional)
# Go to https://github.com/your-org/GesahniV2/releases
```

### For Minor Release:
```bash
# Follow same steps but with feature descriptions
git tag -a v0.6.0 -m "Release v0.6.0: New AI skills and memory integration"
```

## Version Number Guidelines

### Semantic Versioning (Current: v0.5.0)
- **Major**: Breaking changes (v1.0.0)
- **Minor**: New features (v0.6.0)
- **Patch**: Bug fixes, improvements (v0.5.1)

### Pre-release identifiers:
- `v0.6.0-alpha.1` - Alpha testing
- `v0.6.0-beta.1` - Beta testing
- `v0.6.0-rc.1` - Release candidate

## Automation Ideas

### Consider adding:
1. **Automated releases** on successful CI/CD
2. **Changelog generation** from commit messages
3. **Version bumping** in CI pipeline
4. **Release notifications** to Discord/Slack

### Example GitHub Actions workflow:
```yaml
name: Release
on:
  push:
    tags:
      - 'v*.*.*'
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/create-release@v1
        with:
          tag_name: ${{ github.ref }}
          release_name: Release ${{ github.ref }}
```

## Best Practices for Your Project

### Given your rapid development pace:
1. **Release early, release often** - Your 6-day cycle works well
2. **Use descriptive commit messages** - Great for generating changelogs
3. **Tag releases consistently** - You're doing this well
4. **Consider automated testing** before releases
5. **Document breaking changes** clearly

### For feature development:
1. **Use feature branches** for larger changes
2. **Merge to main** when ready for release
3. **Batch related changes** in releases
4. **Test thoroughly** before tagging

## Next Recommended Release

**v0.5.1** - Security hardening and JWT improvements
- Centralized token management
- Runtime JWT strength checks
- Code organization improvements
- Performance optimizations

Ready to release? Run the commands above!
