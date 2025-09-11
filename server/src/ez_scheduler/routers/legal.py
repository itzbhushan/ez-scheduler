"""Legal pages endpoints (privacy policy, terms, etc.)"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(include_in_schema=False)

# Get template directory relative to this file
template_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(template_dir))


@router.get("/privacy-policy")
async def privacy_policy(request: Request):
    """Serve the Privacy Policy page"""
    return templates.TemplateResponse(request, "privacy_policy.html", {})
