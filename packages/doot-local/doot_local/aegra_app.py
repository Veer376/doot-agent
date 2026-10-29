"""FastAPI host for Doot's custom routes when running under Aegra.

Aegra requires the configured custom HTTP app to be a FastAPI instance. Doot's
local server exposes its custom endpoints as a Starlette app, so reuse those
same route objects rather than maintaining a second copy of the handlers.
"""

from fastapi import FastAPI

from doot_local.webapp import app as doot_app


app = FastAPI(title="Doot on Aegra")
app.router.routes.extend(doot_app.routes)

