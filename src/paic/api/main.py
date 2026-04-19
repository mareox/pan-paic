"""FastAPI application entry point.

PAIC v0.2 — stateless query tool.  Mounts:

* ``/healthz``, ``/readyz``, ``/metrics``  (observability)
* ``/api/profiles*``                       (settings-only profile CRUD)
* ``/api/query``, ``/api/query/preview``,
  ``/api/known-prods``                    (stateless query endpoints)
* ``/`` + ``/assets``                      (built SPA bundle, if present)
"""

from fastapi import FastAPI

from paic.api.observability import router as observability_router
from paic.api.profiles import router as profiles_router
from paic.api.reports import router as reports_router
from paic.api.static import mount_static

app = FastAPI(title="Egress IP Condenser", version="0.2.0")

app.include_router(observability_router)
app.include_router(profiles_router)
app.include_router(reports_router)

mount_static(app)
