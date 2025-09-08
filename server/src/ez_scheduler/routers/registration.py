"""Registration form serving endpoints"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from ez_scheduler.backends.email_client import EmailClient
from ez_scheduler.config import config
from ez_scheduler.models.database import get_db
from ez_scheduler.services.llm_service import get_llm_client
from ez_scheduler.services.registration_service import RegistrationService
from ez_scheduler.services.signup_form_service import SignupFormService

router = APIRouter(include_in_schema=False)

# Get template directory relative to this file
template_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(template_dir))

# Configure logging
logging.basicConfig(level=getattr(logging, config["log_level"]))
logger = logging.getLogger(__name__)


@router.get("/form/{url_slug}")
async def serve_registration_form(
    request: Request, url_slug: str, db: Session = Depends(get_db)
):
    """Serve registration form HTML for a given URL slug"""

    signup_form_service = SignupFormService(db)
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
        request,
        "form.html",
        {
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
    db: Session = Depends(get_db),
    llm_client=Depends(get_llm_client),
):
    """Handle registration form submission"""

    # Create services with injected database session
    signup_form_service = SignupFormService(db)
    registration_service = RegistrationService(db, llm_client)
    email_client = EmailClient(config)

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

        # Generate personalized confirmation message using LLM
        confirmation_message = await registration_service.generate_confirmation_message(
            form, name.strip()
        )

        email_sent = False
        # Send confirmation email
        try:
            rsp = await email_client.send_email(
                to=registration.email, text=confirmation_message
            )
            logger.info(f"Email sent successfully: {rsp}")
            email_sent = True
        except RuntimeError as email_error:
            # Log email failure but don't fail registration
            logger.error(
                f"Failed to send confirmation email to {registration.email}: {email_error}"
            )
            # Registration was successful, just email failed
        except ValueError as email_error:
            # Email validation failed
            logger.error(f"Invalid email address {registration.email}: {email_error}")

        # Return JSON success response
        return {
            "success": True,
            "message": confirmation_message,
            "email_sent": email_sent,
            "registration_id": str(registration.id),
        }

    except ValueError as e:
        # Handle validation errors (400 Bad Request)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Handle all other errors (500 Internal Server Error)
        logger.error(f"Error creating registration: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.get("/form/{url_slug}/success", include_in_schema=False)
async def registration_success(
    request: Request,
    url_slug: str,
    registration_id: str,
    db: Session = Depends(get_db),
    llm_client=Depends(get_llm_client),
):
    """Show registration success page"""

    # Create services with injected database session
    signup_form_service = SignupFormService(db)
    registration_service = RegistrationService(db, llm_client)

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
        request,
        "success.html",
        {
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
