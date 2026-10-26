## Directory navigation

 - `generators` The infamous Python configuration generators, bane of the end-user who's used to modifying INI and XML files directly. These are what create the necessary configuration files, controller profiles and any other necessary INI/CFG file an emulator uses upon launching an emulator. Used in conjunction with [ES features](https://github.com/batocera-linux/batocera.linux/blob/master/package/batocera/emulationstation/batocera-es-system/es_features.yml) to make these generated configs based on the options the user has set in ES. A generator is found by name (`<emulator>/<emulator>Generator.py`); `generators/importer.py` only lists the exceptions.
 - Paths used by emulators for their configuration files, saves, etc. live in `retrobox.paths` (`EMULATORS_CONFIG` and friends), not here.
 - `Emulator.py` How do we grab all the settings? And in what order?
 - The launcher itself is `retrobox.launcher` (`bin/retrobox-launch`).
