"""Registration form serving endpoints"""

import logging
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from ez_scheduler.config import config
from ez_scheduler.models.database import get_db
from ez_scheduler.models.field_type import FieldType
from ez_scheduler.models.signup_form import FormStatus
from ez_scheduler.models.timeslot import Timeslot
from ez_scheduler.services.email_service import EmailService
from ez_scheduler.services.form_field_service import FormFieldService
from ez_scheduler.services.llm_service import get_llm_client
from ez_scheduler.services.registration_service import RegistrationService
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.services.timeslot_service import TimeslotService
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
        raise HTTPException(status_code=404, detail="Form not found or archived")

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

    # Timeslots: determine if this is a timeslot form and fetch available slots
    is_timeslot_form = False
    timeslots_grouped: dict[str, list[dict]] = {}
    timeslot_range_display: str | None = None
    try:
        # Check if any timeslots exist for this form
        any_slot = db.exec(
            select(Timeslot.id).where(Timeslot.form_id == form.id).limit(1)
        ).first()
        is_timeslot_form = any_slot is not None

        if is_timeslot_form:
            tz = ZoneInfo(form.time_zone) if form.time_zone else ZoneInfo("UTC")
            ts_service = TimeslotService(db)
            upcoming = ts_service.list_upcoming(form.id)
            # Group by local date string and mark full slots
            for slot in upcoming:
                local_start = slot.start_at.astimezone(tz)
                local_end = slot.end_at.astimezone(tz)
                key = local_start.strftime("%A, %B %d, %Y")
                entry = {
                    "id": str(slot.id),
                    "start": local_start.strftime("%I:%M %p").lstrip("0"),
                    "end": local_end.strftime("%I:%M %p").lstrip("0"),
                    "full": bool(
                        (slot.capacity is not None)
                        and (slot.booked_count is not None)
                        and (slot.booked_count >= slot.capacity)
                    ),
                }
                timeslots_grouped.setdefault(key, []).append(entry)

            # Build a friendly date range header for timeslot forms with slots
            if upcoming:
                earliest_local = min(s.start_at for s in upcoming).astimezone(tz)
                latest_local = max(s.end_at for s in upcoming).astimezone(tz)

                def _fmt_range(a, b):
                    # a, b are local datetimes
                    ad, bd = a.date(), b.date()
                    if ad == bd:
                        return a.strftime("%B %d, %Y")
                    if ad.year == bd.year:
                        if ad.month == bd.month:
                            # Same month, same year: "Sep 26–30, 2025"
                            return f"{a.strftime('%B')} {ad.day}–{bd.day}, {ad.year}"
                        # Same year different months: "Sep 26 – Oct 10, 2025"
                        return f"{a.strftime('%B')} {ad.day} – {b.strftime('%B')} {bd.day}, {ad.year}"
                    # Different years: "Dec 29, 2025 – Jan 03, 2026"
                    return f"{a.strftime('%B')} {ad.day}, {ad.year} – {b.strftime('%B')} {bd.day}, {bd.year}"

                timeslot_range_display = _fmt_range(earliest_local, latest_local)
    except Exception:
        # If any error occurs in timeslot handling, fall back to standard form
        is_timeslot_form = False

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
            "is_timeslot_form": is_timeslot_form,
            "timeslots_grouped": timeslots_grouped,
            "timeslot_range_display": timeslot_range_display,
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
    email_service = EmailService(llm_client, config)
    timeslot_service = TimeslotService(db)

    # Get the form by URL slug
    form = signup_form_service.get_form_by_url_slug(url_slug)

    if not form:
        raise HTTPException(status_code=404, detail="Form not found or archived")
    # Block submissions for draft forms
    if form.status != FormStatus.PUBLISHED:
        raise HTTPException(
            status_code=403, detail="Form is not accepting registrations"
        )

    # Parse form data
    form_data = await request.form()

    # Extract standard fields
    name = form_data.get("name", "").strip()
    email = form_data.get("email", "").strip().lower()
    phone = form_data.get("phone", "").strip()
    rsvp_response = form_data.get("rsvp_response")  # "yes", "no", or None

    logger.info(f"Submitting registration for form: {url_slug} with data: {form_data}")

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
                # Enforce fewer than 250 characters for text fields
                if field_value and len(str(field_value)) > 250:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{field.label} must be fewer than 250 characters",
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

    # Handle timeslot selection if this is a timeslot form
    # Determine if any timeslots exist for this form
    has_timeslots = (
        db.exec(select(Timeslot.id).where(Timeslot.form_id == form.id).limit(1)).first()
        is not None
    )

    # Always read submitted timeslot IDs (if any)
    selected_timeslot_ids: list[str] = form_data.getlist("timeslot_ids")
    if selected_timeslot_ids and not has_timeslots:
        # Timeslots submitted but the form doesn't support timeslots
        raise HTTPException(
            status_code=403,
            detail="One or more selected timeslots are invalid for this form.",
        )
    if has_timeslots and not selected_timeslot_ids:
        raise HTTPException(
            status_code=400, detail="Please select at least one timeslot."
        )

    # Store RSVP response if provided (for RSVP yes/no forms)
    if rsvp_response:
        additional_data["rsvp_response"] = rsvp_response

        # Reset guest count to 0 if user RSVPs "no"
        if rsvp_response == "no":
            additional_data["guest_count"] = "0"

        if rsvp_response == "yes":
            if "guest_count" not in additional_data:
                additional_data["guest_count"] = "1"

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

        # If this is a timeslot form, attempt to book selected slots
        booked_slot_ids: list[str] = []
        selected_slot_lines: list[str] | None = None
        if has_timeslots and selected_timeslot_ids:
            # Validate that all provided IDs belong to this form
            # Fetch set of provided ids that belong to the form
            provided_ids = {sid for sid in selected_timeslot_ids}
            rows = db.exec(
                select(Timeslot.id).where(
                    Timeslot.form_id == form.id, Timeslot.id.in_(provided_ids)
                )
            ).all()
            form_owned_ids = {str(r[0] if isinstance(r, tuple) else r) for r in rows}
            if form_owned_ids != provided_ids:
                raise HTTPException(
                    status_code=403,
                    detail="One or more selected timeslots are invalid for this form.",
                )

            # Book
            # Convert to UUIDs
            slot_uuids = [
                (
                    __import__("uuid").UUID(s)
                    if not isinstance(s, str)
                    else __import__("uuid").UUID(s)
                )
                for s in selected_timeslot_ids
            ]
            booking = timeslot_service.book_slots(registration.id, slot_uuids)
            if not booking.success:
                # 409 Conflict with minimal details to avoid leaking booking state
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "One or more selected timeslots are no longer available. Please refresh and try again.",
                    },
                )
            booked_slot_ids = [str(x) for x in booking.booked_ids]

            # Prepare human-readable lines for the booked timeslots for emails
            def _format_lines(rows, tzinfo):
                lines = []
                for r in rows:
                    start_local = r.start_at.astimezone(tzinfo)
                    end_local = r.end_at.astimezone(tzinfo)
                    day = start_local.strftime("%a %b %d").replace(" 0", " ")
                    start_str = start_local.strftime("%I:%M %p").lstrip("0")
                    end_str = end_local.strftime("%I:%M %p").lstrip("0")
                    lines.append(f"{day}, {start_str}–{end_str}")
                return lines

            rows = db.exec(
                select(Timeslot).where(
                    Timeslot.id.in_(
                        [__import__("uuid").UUID(x) for x in booked_slot_ids]
                    )
                )
            ).all()
            rows_sorted = sorted(rows, key=lambda r: r.start_at)

            # Resolve timezone with fallback to UTC on invalid tz
            try:
                tz = ZoneInfo(form.time_zone) if form.time_zone else ZoneInfo("UTC")
            except ZoneInfoNotFoundError:
                logger.warning(
                    "Invalid form time_zone '%s' for form_id=%s; falling back to UTC",
                    form.time_zone,
                    form.id,
                )
                tz = ZoneInfo("UTC")
            except Exception:
                logger.exception(
                    "Failed to load time_zone '%s' for form_id=%s",
                    form.time_zone,
                    form.id,
                )
                tz = ZoneInfo("UTC")

            try:
                selected_slot_lines = _format_lines(rows_sorted, tz)
            except Exception:
                logger.exception(
                    "Failed to format selected timeslots with tz=%s; falling back to UTC",
                    getattr(tz, "key", str(tz)),
                )
                try:
                    selected_slot_lines = _format_lines(rows_sorted, ZoneInfo("UTC"))
                except Exception:
                    logger.exception("Failed to format selected timeslots even in UTC")
                    selected_slot_lines = None

        # Generate fallback confirmation message for response
        confirmation_message = await registration_service.generate_confirmation_message(
            form, name.strip(), rsvp_response
        )

        # Send confirmation email using EmailService
        form_url = f"{request.base_url}form/{url_slug}"
        email_sent = await email_service.notify_registration_user(
            form=form,
            registration=registration,
            form_url=str(form_url),
            selected_slot_lines=selected_slot_lines,
        )

        # Send creator notification email
        creator_notification_sent = await email_service.notify_creator(
            form=form,
            registration=registration,
            selected_slot_lines=selected_slot_lines,
        )

        # Return JSON success response
        return {
            "success": True,
            "message": confirmation_message,
            "email_sent": email_sent,
            "creator_notification_sent": creator_notification_sent,
            "registration_id": str(registration.id),
            "timeslot_ids": booked_slot_ids,
        }

    except ValueError as e:
        # Handle validation errors (400 Bad Request)
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        # Propagate HTTP exceptions such as 403/409 we intentionally raised
        raise
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
