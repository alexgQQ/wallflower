import subprocess

# There is a bit of a hack here to get a correct version between dev envs
# and full releases. I ran into this as I wanted a single source for the app version
# but didn't want to ship additional files (pyproject) with the build.
# In debug/dev mode by default the module version will pull
# the git short sha. When running `make pkg` the line below is instead replaced
# with the poetry version like __version = '0.1.0'.
__version__ = subprocess.check_output(["git", "describe", "--always"]).strip().decode()
