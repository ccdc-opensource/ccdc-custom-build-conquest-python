# Introduction 
This repository contains scripts used to generate conquest's python distribution

# Build and Test

- Run python3 build_conquest_python.py
- Use an administrator account on windows
- or just file a PR

# Origin of things

With things being kept in azure devops artefacts, it's useful to know where things are coming from...

- Python interpreter was fetched from the canonical url: https://www.python.org/ftp/python/
- apsw was fetched from the github releases: https://github.com/rogerbinns/apsw/releases/
- BSDDB3 was obtained from: https://www.lfd.uci.edu/~gohlke/pythonlibs/#bsddb3
- See https://stackoverflow.com/questions/33714698/installing-bsddb3-6-1-1-in-windows-filenotfounderror-db-include-db-h
- Togl is no longer maintained so I took some time to create a new repository for it, import the various releases that came in time and made it build on all platforms using ci.
  - The repository can be found here: https://github.com/rockdreamer/togl
  - the build we are using is this one: https://ci.appveyor.com/project/rockdreamer/togl/build/job/yvhnhasfenv955m9/artifacts
