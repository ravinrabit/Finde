#!/usr/bin/env python
"""Utilitário de linha de comando do Django."""

import os
import sys


def main():
    # "manage.py test" sempre usa setup/settings/test.py, sem depender de .env.
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        os.environ.setdefault("DJANGO_ENV", "test")

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "setup.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
