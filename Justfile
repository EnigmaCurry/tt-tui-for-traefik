# Default target
default: help

# Show available commands
help:
    @just --list

# Run the application
run *ARGS:
    uv run tt {{ARGS}}

# Bump version, commit, and tag a release (e.g., just release 0.2.0)
release VERSION:
    #!/usr/bin/env bash
    set -euo pipefail

    # Validate version format
    if ! [[ "{{VERSION}}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "Error: Version must be in format X.Y.Z (e.g., 0.2.0)"
        exit 1
    fi

    # Check for uncommitted changes
    if ! git diff --quiet || ! git diff --cached --quiet; then
        echo "Error: Working directory has uncommitted changes"
        exit 1
    fi

    # Update version in pyproject.toml
    sed -i 's/^version = ".*"/version = "{{VERSION}}"/' pyproject.toml

    # Commit and tag
    git add pyproject.toml
    git commit -m "Release v{{VERSION}}"
    git tag "v{{VERSION}}"

    echo "Released v{{VERSION}}"
    echo "Run 'git push origin master --tags' to publish"
