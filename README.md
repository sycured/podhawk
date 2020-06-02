# podhawk

Podhawk allows you to keep image and container up-to-date

## How it works ?
You need to execute Podhawk with same user running containers.

1. list containers and keep actually running in variable
2. list images (name and tag)
3. pull all images
4. recreate containers using new images

## Requirements
- Podman in your $PATH
- Python 3.8+ (stdlib only)

## Notes
- PEP8 and complexity tested via `flake8 --max-complexity 5`