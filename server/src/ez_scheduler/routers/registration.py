"""Registration form serving endpoints"""

import logging
from pathlib import Path

from ez_scheduler.config import config
from ez_scheduler.models.database import get_db
from ez_scheduler.services.registration_service import RegistrationService
from ez_scheduler.services.signup_form_service import SignupFormService
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()

# Get template directory relative to this file
template_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(template_dir))

db_session = next(get_db())
signup_form_service = SignupFormService(db_session)
registration_service = RegistrationService(db_session)

# Configure logging
logging.basicConfig(level=getattr(logging, config["log_level"]))
logger = logging.getLogger(__name__)


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


@router.post("/form/{url_slug}")
async def submit_registration_form(
    request: Request,
    url_slug: str,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
):
    """Handle registration form submission"""

    # Get the form by URL slug
    form = signup_form_service.get_form_by_url_slug(url_slug)

    logger.info(f"Submitting registration for form: {url_slug}")

    if not form:
        raise HTTPException(status_code=404, detail="Form not found or inactive")

    try:
        logger.info(
            f"Creating registration with form_id={form.id}, name='{name}', email='{email}', phone='{phone}'"
        )

        # Create the registration
        registration = registration_service.create_registration(
            form_id=form.id,
            name=name.strip(),
            email=email.strip().lower(),
            phone=phone.strip(),
        )

        logger.info(f"Created registration {registration.id} for form {form.id}")

        # Return JSON success response
        return {
            "success": True,
            "message": "Registration submitted successfully",
            "registration_id": str(registration.id),
        }

    except Exception as e:
        logger.error(f"Error creating registration: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/form/{url_slug}/success")
async def registration_success(request: Request, url_slug: str, registration_id: str):
    """Show registration success page"""

    # Get the form by URL slug
    form = signup_form_service.get_form_by_url_slug(url_slug)

    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    # Verify registration exists
    try:
        registration = registration_service.get_registration_by_id(registration_id)
        if not registration or registration.form_id != form.id:
            raise HTTPException(status_code=404, detail="Registration not found")
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid registration ID")

    return templates.TemplateResponse(
        "success.html",
        {
            "request": request,
            "form": form,
            "registration": registration,
            "formatted_date": form.event_date.strftime("%B %d, %Y"),
            "formatted_start_time": (
                form.start_time.strftime("%I:%M %p") if form.start_time else None
            ),
            "formatted_end_time": (
                form.end_time.strftime("%I:%M %p") if form.end_time else None
            ),
        },
    )
