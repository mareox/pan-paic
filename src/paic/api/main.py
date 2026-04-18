"""FastAPI application entry point."""

from fastapi import FastAPI

from paic.api.diffs import router as diffs_router
from paic.api.email_recipients import router as email_recipients_router
from paic.api.observability import router as observability_router
from paic.api.profiles import router as profiles_router
from paic.api.reports import router as reports_router
from paic.api.static import mount_static
from paic.api.tenants import router as tenants_router
from paic.api.webhooks import router as webhooks_router

app = FastAPI(title="Prisma Access IP Console", version="0.1.0")

app.include_router(observability_router)
app.include_router(tenants_router)
app.include_router(profiles_router)
app.include_router(reports_router)
app.include_router(diffs_router)
app.include_router(webhooks_router)
app.include_router(email_recipients_router)

mount_static(app)
