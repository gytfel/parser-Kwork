import sys

if sys.version_info < (3, 10):
    sys.exit(f"Нужен Python 3.10 или новее, а у вас {sys.version.split()[0]}")

from kwork_bot.cli import main  # noqa: E402

sys.exit(main())
