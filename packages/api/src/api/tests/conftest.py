import os

# Set environment to testing BEFORE importing any application code
# This must happen before settings are loaded
# Note: Settings uses GOLFCART_ prefix, so we need GOLFCART_ENV not ENV
os.environ["GOLFCART_ENV"] = "testing"


from api.tests.fixtures import *  # noqa: F403
