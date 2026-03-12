# Publishing Runbook

Checklist for publishing a new version of the ice9 SDK to PyPI.

## Pre-Publish Checklist

### 1. Version and Changelog
- [ ] Update version in `pyproject.toml`
- [ ] Update version in `ice9/__init__.py`
- [ ] Add entry to `CHANGELOG.md` with:
  - Version number and date
  - Added/Changed/Fixed/Removed sections
  - Clear descriptions of what changed and why

### 2. Code Quality
- [ ] Run full test suite: `pytest tests/`
- [ ] All tests passing (140+ tests)
- [ ] No new warnings introduced
- [ ] Run integration tests if API key available: `ICE9_API_KEY=... pytest tests/integration/ -v`

### 3. Documentation
- [ ] README reflects any new features
- [ ] Examples are up-to-date
- [ ] Docstrings updated for any changed methods
- [ ] Timing/performance claims match reality (check benchmarks)

### 4. Review Changes
- [ ] Review `git diff` to ensure no debug code, TODOs, or secrets
- [ ] Check that all new features have tests
- [ ] Verify backwards compatibility (or document breaking changes)

### 5. Local Testing
- [ ] Test import in fresh environment: `python -c "from ice9 import Ice9, AsyncIce9"`
- [ ] Run one of the examples: `python examples/free_tier.py <test_image>`
- [ ] Verify version: `python -c "import ice9; print(ice9.__version__)"`

## Publishing Steps

### 1. Clean Build Artifacts
```bash
rm -rf dist/ build/ *.egg-info
```

### 2. Build Package
```bash
source venv/bin/activate
python -m build
```

**Expected output:**
- `dist/ice9-X.Y.Z.tar.gz` (source distribution)
- `dist/ice9-X.Y.Z-py3-none-any.whl` (wheel)

### 3. Inspect Build
```bash
ls -lh dist/
tar -tzf dist/ice9-*.tar.gz | head -20  # Check contents
```

**Verify:**
- [ ] Correct version in filenames
- [ ] Package includes: `ice9/`, `tests/`, `README.md`, `LICENSE`, `CHANGELOG.md`
- [ ] No `.pyc` files or `__pycache__` directories
- [ ] No secrets or `.env` files

### 4. Upload to PyPI
```bash
export $(cat .env | grep TWINE_PASSWORD | xargs)
python -m twine upload dist/* --username __token__
```

**Monitor for:**
- Upload progress for both `.whl` and `.tar.gz`
- Success message with PyPI URL
- Any authentication errors

### 5. Verify Upload
Open the PyPI page: https://pypi.org/project/ice9/X.Y.Z/

**Check:**
- [ ] Version number is correct
- [ ] README renders properly (markdown formatting)
- [ ] All classifiers are correct
- [ ] Dependencies listed correctly
- [ ] Download links work

## Post-Publish Verification

### 1. Install from PyPI
```bash
# In a fresh virtualenv or separate directory
pip install ice9==X.Y.Z

# Verify version
python -c "import ice9; print(ice9.__version__)"

# Quick smoke test
python -c "from ice9 import Ice9, AsyncIce9; print('✓ Both clients importable')"
```

### 2. Test in Real Environment
- [ ] Update version in a dependent project (e.g., Ballgown)
- [ ] Run their tests
- [ ] Verify no breaking changes

### 3. Git Tag and Push
```bash
git tag v0.0.X
git push origin main
git push origin v0.0.X
```

### 4. Announce
- [ ] Update any documentation sites
- [ ] Notify users in #announcements (if applicable)
- [ ] Update Ballgown/other internal projects

## Rollback Procedure

If a release has critical bugs:

### Option 1: Yank the Release (Preferred)
```bash
# Marks version as broken on PyPI, prevents new installs
twine upload --skip-existing  # No-op, just to authenticate
# Then manually yank on PyPI web interface
```

Navigate to https://pypi.org/project/ice9/X.Y.Z/ → Manage → Yank release

### Option 2: Publish Hotfix
1. Branch from the bad release: `git checkout v0.0.X`
2. Fix the critical bug
3. Bump patch version (e.g., 0.0.3 → 0.0.4)
4. Publish hotfix following this runbook

### Option 3: Revert and Republish
1. `git revert <bad-commit>`
2. Bump version
3. Publish following this runbook

**Note:** You cannot delete or replace a version on PyPI. Once published, that version number is permanent.

## Common Issues

### Build fails with "version already exists"
- You forgot to bump the version number
- Fix: Update version in `pyproject.toml` and `ice9/__init__.py`

### Upload fails with authentication error
- Check that `TWINE_PASSWORD` is set correctly
- Verify the PyPI token hasn't expired
- Make sure you're using `--username __token__`

### Tests fail after upgrade
- Check CHANGELOG for breaking changes
- Review migration guide (if applicable)
- Check if default behavior changed

### README doesn't render on PyPI
- Markdown must be GitHub-flavored
- Check for unsupported syntax
- Test locally: `python -m readme_renderer README.md`

## Version Numbering Guide

We use `0.x.y` until the API stabilizes:
- `0.x.0` - New features, might have breaking changes
- `0.0.y` - Bug fixes, docs, non-breaking improvements

Breaking changes are OK in 0.x, but should be documented clearly.

After 1.0, use semantic versioning strictly:
- `1.0.0` - Initial stable release
- `1.1.0` - New features (backwards compatible)
- `1.0.1` - Bug fixes only
- `2.0.0` - Breaking changes

## Emergency Contacts

- PyPI account owner: [Your email]
- API maintainer: [Your email]
- Backup publish credentials: `.env` file (keep secure!)

## Notes for Future Improvements

- [ ] Set up GitHub Actions for automated testing
- [ ] Add pre-commit hooks for version checks
- [ ] Create a `make publish` target that runs this checklist
- [ ] Set up TestPyPI for staging releases
