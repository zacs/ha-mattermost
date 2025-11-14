# Continuous Integration

This repository uses GitHub Actions for automated validation, testing, and quality checks.

## Workflows

### Validation Workflow (`.github/workflows/validate.yml`)

Runs on every push and pull request to `main`/`master` branches.

**Jobs:**

1. **HACS Validation** - Validates integration for HACS compatibility
2. **Hassfest Validation** - Home Assistant official integration validator
3. **Code Style Checks** - Black formatting and isort import sorting
4. **Import Validation** - Ensures Python imports work correctly
5. **Linting** - Flake8 code quality checks

### Release Workflow (`.github/workflows/release.yml`)

Runs when a GitHub release is published.

**Jobs:**

1. **Release Validation** - Full validation suite for releases
2. **Code Quality** - Ensures release meets formatting standards
3. **Structure Check** - Validates integration file structure

## Code Quality Standards

### Black Formatting
- Line length: 88 characters
- Python 3.11+ target
- Configuration in `pyproject.toml`

### Import Sorting (isort)
- Black-compatible profile
- Configuration in `.isort.cfg`
- Home Assistant imports properly categorized

### Linting (flake8)
- Checks for syntax errors and undefined names
- Focuses on critical issues (E9, F63, F7, F82)

## Local Development

### Code Formatting
```bash
# Format code with Black
black .

# Sort imports with isort
isort .

# Check formatting without changes
black --check --diff .
isort --check-only --diff .
```

### Linting
```bash
# Run flake8 linting
flake8 custom_components/ --count --select=E9,F63,F7,F82 --show-source --statistics
```

### Basic Validation
```bash
# Check that required files exist
test -f custom_components/mattermost/manifest.json && echo "✓ Files present"

# Validate JSON files
python3 -c "import json; json.load(open('custom_components/mattermost/manifest.json'))"
python3 -c "import json; json.load(open('custom_components/mattermost/translations/en.json'))"
```

## Integration Standards

The CI/CD pipeline ensures:

- ✅ **HACS Compatibility** - Integration can be installed via HACS
- ✅ **Home Assistant Standards** - Passes official hassfest validation
- ✅ **Code Quality** - Consistent formatting and import organization
- ✅ **File Structure** - All required files present and valid
- ✅ **Import Validation** - Python modules import correctly
- ✅ **JSON Validation** - Configuration files are well-formed

## Contribution Guidelines

1. **Format Code** - Use Black and isort before committing
2. **Check Imports** - Ensure your code imports correctly
3. **Follow Standards** - Adhere to Home Assistant integration guidelines
4. **Check CI** - All GitHub Actions checks must pass before merging

## Badges

Add these to your README.md to show CI status:

```markdown
[![Validate](https://github.com/yourusername/ha-mattermost/actions/workflows/validate.yml/badge.svg)](https://github.com/yourusername/ha-mattermost/actions/workflows/validate.yml)
[![HACS](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)
```