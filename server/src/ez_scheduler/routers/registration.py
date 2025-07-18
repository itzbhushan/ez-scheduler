"""Registration form serving endpoints"""

from pathlib import Path

from ez_scheduler.models.database import get_db
from ez_scheduler.services.signup_form_service import SignupFormService
from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

router = APIRouter()

# Get the absolute path to the templates directory
# Check if running in container (/app) or local development
if Path("/app/templates").exists():
    # Running in Docker container
    template_dir = Path("/app/templates")
else:
    # Running locally - relative to server directory
    template_dir = Path(__file__).parent.parent.parent.parent / "templates"

templates = Jinja2Templates(directory=str(template_dir))

db_session = next(get_db())
signup_form_service = SignupFormService(db_session)


@router.get("/form/{url_slug}")
async def serve_registration_form(request: Request, url_slug: str):
    """Serve registration form HTML for a given URL slug"""

    form = signup_form_service.get_form_by_url_slug(url_slug)

    if not form:
        raise HTTPException(status_code=404, detail="Form not found or inactive")

    # Format date and times for display
    formatted_date = form.event_date.strftime("%B %d, %Y")
    formatted_start_time = (
        form.start_time.strftime("%I:%M %p") if form.start_time else None
    )
    formatted_end_time = form.end_time.strftime("%I:%M %p") if form.end_time else None

    return templates.TemplateResponse(
        "form.html",
        {
            "request": request,
            "form": form,
            "url_slug": url_slug,
            "formatted_date": formatted_date,
            "formatted_start_time": formatted_start_time,
            "formatted_end_time": formatted_end_time,
        },
    )
