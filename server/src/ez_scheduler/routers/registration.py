"""Registration form serving endpoints"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from ez_scheduler.backends.email_client import EmailClient
from ez_scheduler.config import config
from ez_scheduler.models.database import get_db
from ez_scheduler.models.field_type import FieldType
from ez_scheduler.services.form_field_service import FormFieldService
from ez_scheduler.services.llm_service import get_llm_client
from ez_scheduler.services.registration_service import RegistrationService
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.utils.address_utils import generate_google_maps_url

router = APIRouter(include_in_schema=False)

# Get template directory relative to this file
template_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(template_dir))

# Configure logging
logging.basicConfig(level=getattr(logging, config["log_level"]))
logger = logging.getLogger(__name__)


@router.get("/form/{url_slug}")
async def serve_registration_form(
    request: Request,
    url_slug: str,
    db: Session = Depends(get_db),
    theme: str | None = None,
):
    """Serve registration form HTML for a given URL slug"""

    signup_form_service = SignupFormService(db)
    form = signup_form_service.get_form_by_url_slug(url_slug)

    if not form:
        raise HTTPException(status_code=404, detail="Form not found or inactive")

    # Get custom fields for this form
    form_field_service = FormFieldService(db)
    custom_fields = form_field_service.get_fields_by_form_id(form.id)

    # Format date and times for display
    formatted_date = form.event_date.strftime("%B %d, %Y")
    formatted_start_time = (
        form.start_time.strftime("%I:%M %p") if form.start_time else None
    )
    formatted_end_time = form.end_time.strftime("%I:%M %p") if form.end_time else None

    # Generate Google Maps URL for the location
    google_maps_url = generate_google_maps_url(form.location)

    # Resolve theme: query param overrides env default
    resolved_theme = theme or config.get("default_form_theme")
    template_name = (
        "themes/golu_form.html"
        if resolved_theme and resolved_theme.lower() == "golu"
        else "form.html"
    )

    return templates.TemplateResponse(
        request,
        template_name,
        {
            "form": form,
            "url_slug": url_slug,
            "custom_fields": custom_fields,
            "formatted_date": formatted_date,
            "formatted_start_time": formatted_start_time,
            "formatted_end_time": formatted_end_time,
            "google_maps_url": google_maps_url,
        },
    )


@router.post("/form/{url_slug}")
async def submit_registration_form(
    request: Request,
    url_slug: str,
    db: Session = Depends(get_db),
    llm_client=Depends(get_llm_client),
):
    """Handle registration form submission"""

    # Create services with injected database session
    signup_form_service = SignupFormService(db)
    registration_service = RegistrationService(db, llm_client)
    form_field_service = FormFieldService(db)
    email_client = EmailClient(config)

    # Get the form by URL slug
    form = signup_form_service.get_form_by_url_slug(url_slug)

    logger.info(f"Submitting registration for form: {url_slug}")

    if not form:
        raise HTTPException(status_code=404, detail="Form not found or inactive")

    # Parse form data
    form_data = await request.form()

    # Extract standard fields
    name = form_data.get("name", "").strip()
    email = form_data.get("email", "").strip().lower()
    phone = form_data.get("phone", "").strip()
    rsvp_response = form_data.get("rsvp_response")  # "yes", "no", or None

    # Validate required standard fields
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    # Validate that at least one contact method is provided
    if not email and not phone:
        raise HTTPException(
            status_code=400,
            detail="Please provide either an email address or phone number.",
        )

    # Get custom fields for validation and processing
    custom_fields = form_field_service.get_fields_by_form_id(form.id)

    # Extract and validate custom field data
    additional_data = {}
    for field in custom_fields:
        field_value = form_data.get(field.field_name)

        # Handle different field types
        if field.field_type == FieldType.CHECKBOX:
            # Checkbox fields send 'true' when checked, None when unchecked
            field_value = field_value == "true" if field_value is not None else False
        elif field_value is not None:
            field_value = str(field_value).strip()

        # Validate field type-specific constraints
        if field_value is not None and field_value != "":
            if field.field_type == FieldType.NUMBER:
                try:
                    float(field_value)
                except ValueError:
                    raise HTTPException(
                        status_code=400, detail=f"{field.label} must be a valid number"
                    )
            elif field.field_type == FieldType.SELECT and field.options:
                if field_value not in field.options:
                    raise HTTPException(
                        status_code=400, detail=f"Invalid option for {field.label}"
                    )
            elif field.field_type == FieldType.TEXT:
                # Enforce fewer than 250 words for text fields
                word_count = len(str(field_value).split())
                if word_count >= 250:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{field.label} must be fewer than 250 words",
                    )

        # Validate required fields
        if field.is_required:
            if field.field_type == FieldType.CHECKBOX and not field_value:
                raise HTTPException(
                    status_code=400, detail=f"{field.label} is required"
                )
            elif field.field_type != FieldType.CHECKBOX and (
                not field_value or field_value == ""
            ):
                raise HTTPException(
                    status_code=400, detail=f"{field.label} is required"
                )

        # Store field data if provided
        if field_value is not None and (
            field.field_type == FieldType.CHECKBOX or field_value != ""
        ):
            additional_data[field.field_name] = field_value

    # Store RSVP response if provided (for RSVP yes/no forms)
    if rsvp_response:
        additional_data["rsvp_response"] = rsvp_response

    try:
        logger.info(
            f"Creating registration with form_id={form.id}, name='{name}', email='{email}', phone='{phone}', additional_data={additional_data}"
        )

        # Create the registration
        registration = registration_service.create_registration(
            form_id=form.id,
            name=name,
            email=email,
            phone=phone,
            additional_data=additional_data if additional_data else None,
        )

        logger.info(f"Created registration {registration.id} for form {form.id}")

        # Generate personalized confirmation message using LLM
        confirmation_message = await registration_service.generate_confirmation_message(
            form, name.strip()
        )

        email_sent = False
        # Send confirmation email only if email was provided
        if email:
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
                logger.error(
                    f"Invalid email address {registration.email}: {email_error}"
                )
        else:
            logger.info("No email provided, skipping email confirmation")

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

    # Generate Google Maps URL for the location
    google_maps_url = generate_google_maps_url(form.location)

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
            "google_maps_url": google_maps_url,
        },
    )
