"""Retrobox store: content (music, bezels, shaders, homebrew...) from a package repository.

EmulationStation's "Content Downloader" runs ``retrobox-store`` (see
``bin/retrobox-store``) the way batocera's runs ``batocera-store``. The
repository is batocera's (a pacman repository: a sync database and the package
files), but no pacman is needed: ``catalog`` reads the database, ``store``
downloads, checks and unpacks the packages (``extract``), and ``state`` keeps
what is installed so it can be removed or updated.
"""
