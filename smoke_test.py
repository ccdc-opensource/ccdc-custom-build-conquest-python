import errno
import os
import platform

# there should be no issues importing sqlite libraries
import sqlite3
import distutils.version
# Ensure we haven't inadvertently got the (ancient) system SQLite
assert distutils.version.LooseVersion('3.7.4') <= distutils.version.LooseVersion(sqlite3.sqlite_version)
sqlite3.connect(":memory:")

# pyenv has trouble building the tkinter extension, so checking for that
# this tends to happen on macos, where even the exception handling below
# will error out as _tkinter is not present
# On Linux, the import can fail because DISPLAY is not set. In this case
# a TclError is raised. But if we have that, we're good to go.
try:
    import Tkinter
except _tkinter.TclError:
    print("no display, but that's ok")

# Tkinter.Tk()

from bsddb3 import db
dbenv = db.DBEnv()
dbenv.set_cachesize(0,4096000,1)
envname = 'dbenv.removeme'
try:
    os.mkdir(envname)
except OSError as exc:
    if exc.errno != errno.EEXIST:
        raise
    pass
dbenv.open(envname, db.DB_INIT_MPOOL | db.DB_CREATE)

print('python interpreter smoke test ok')
