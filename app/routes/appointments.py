from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models import Appointment, Availability, User
from app.schemas import AppointmentCreate
from app.db import get_db
from datetime import datetime
from fastapi_jwt_auth import AuthJWT
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter()

class Settings(BaseModel):
    authjwt_secret_key: str = "admin123"  # Replace with a strong secret key
    authjwt_algorithm: str = "HS256"

# Load the configuration
@AuthJWT.load_config
def get_config():
    return Settings()

@router.post("/appointments")
def book_appointment(
    appointment: AppointmentCreate,
    db: Session = Depends(get_db),
    Authorize: AuthJWT = Depends()
):
    try:
        # Step 1: Ensure the user is authorized
        Authorize.jwt_required()
        student_id = int(Authorize.get_jwt_subject())
        user_role = Authorize.get_raw_jwt().get("role")

        if user_role != "student":
            raise HTTPException(status_code=403, detail="Only students can book appointments")

        # Step 2: Verify the professor exists
        professor = db.query(User).filter(
            User.id == appointment.professor_id, User.role == "professor"
        ).first()
        if not professor:
            raise HTTPException(status_code=404, detail="Professor not found")

        # Step 3: Ensure the student is booking for themselves
        if student_id != appointment.student_id:
            raise HTTPException(status_code=403, detail="You can only book appointments for yourself")

        # Step 4: Validate the time slot provided
        try:
            start_time = datetime.fromisoformat(appointment.start_time)
            end_time = datetime.fromisoformat(appointment.end_time)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid time format for start_time or end_time")

        if start_time >= end_time:
            raise HTTPException(status_code=400, detail="Start time must be earlier than end time")

        # Step 5: Check professor's availability for the requested slot
        available_slots = db.query(Availability).filter(
            Availability.professor_id == appointment.professor_id
        ).all()

        # Ensure that the requested time slot is completely covered by one of the professor's availability slots
        slot_found = any(
            slot.start_time <= start_time and slot.end_time >= end_time for slot in available_slots
        )
        if not slot_found:
            raise HTTPException(
                status_code=409,
                detail="Requested time is outside the professor's availability slots"
            )

        # Step 6: Ensure no overlapping appointments
        

        # Step 7: Save the appointment if all checks pass
        new_appointment = Appointment(
            professor_id=appointment.professor_id,
            student_id=appointment.student_id,
            start_time=start_time,
            end_time=end_time,
            is_canceled=False
        )
        db.add(new_appointment)
        db.commit()
        db.refresh(new_appointment)

        # Step 8: Update professor's availability
        for slot in available_slots:
            if slot.start_time == start_time and slot.end_time == end_time:
                # Remove the exact match slot (fully booked)
                db.delete(slot)
            elif start_time > slot.start_time and end_time < slot.end_time:
                # Case 1: Split the availability into two parts
                new_slot1 = Availability(
                    professor_id=appointment.professor_id,
                    start_time=slot.start_time,
                    end_time=start_time
                )
                new_slot2 = Availability(
                    professor_id=appointment.professor_id,
                    start_time=end_time,
                    end_time=slot.end_time
                )
                db.add(new_slot1)
                db.add(new_slot2)

                # Delete the original slot after creating the two new slots
                db.delete(slot)
            elif start_time == slot.start_time:
                # Case 2: Shrink the slot to start after the appointment
                slot.start_time = end_time
            elif end_time == slot.end_time:
                # Case 3: Shrink the slot to end before the appointment
                slot.end_time = start_time

        # Commit all changes to the database
        db.commit()
        

        return {"appointment booked successfully for id": new_appointment.id}

    except SQLAlchemyError as db_error:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error occurred: {str(db_error)}")
    except Exception as error:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(error)}")


@router.put("/appointments/{appointmentid}")
def cancel_appointment(
    appointmentid: int,
    db: Session = Depends(get_db),
    Authorize: AuthJWT = Depends(),
):
    # Require JWT authorization
    Authorize.jwt_required()

    # Extract professor ID and role from the JWT
    professor_id = int(Authorize.get_jwt_subject())
    print("Professor ID:", professor_id)  # 'sub' field in the token
    raw_jwt = Authorize.get_raw_jwt()
    role = raw_jwt.get("role")

    # Ensure the user is a professor
    if role != "professor":
        raise HTTPException(
            status_code=403, detail="Only professors can cancel appointments"
        )

    # Fetch the appointment from the database
    appointment = db.query(Appointment).filter(Appointment.id == appointmentid).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Ensure the professor owns the appointment
    if appointment.professor_id != professor_id:
        raise HTTPException(
            status_code=403, detail="You can only cancel your own appointments"
        )

    # Update the appointment status
    appointment.is_canceled = True
    db.commit()
    db.refresh(appointment)  # Refresh the object to ensure it's up-to-date

    return {
        "message": "Appointment canceled successfully",
        "appointment_id": appointmentid,
        "is_canceled": appointment.is_canceled,
    }


@router.get("/getappointments")
def bookings(Authorize: AuthJWT = Depends(), db: Session = Depends(get_db)):
    Authorize.jwt_required()
    user_id = int(Authorize.get_jwt_subject())
    raw_jwt = Authorize.get_raw_jwt()
    role = raw_jwt.get("role")

    if role == "professor":
        appointments = db.query(Appointment).filter(
            Appointment.professor_id == user_id, Appointment.is_canceled == False
        ).all()
    elif role == "student":
        appointments = db.query(Appointment).filter(
            Appointment.student_id == user_id, Appointment.is_canceled == False
        ).all()
    else:
        raise HTTPException(status_code=403, detail="Unauthorized role")

    if not appointments:
        return {"appointments": []}

    appointment_data = [
        {
            "appointment_id": appointment.id,
            "student_id": appointment.student_id,
            "professor_id": appointment.professor_id,
            "start_time": appointment.start_time.isoformat(),
            "end_time": appointment.end_time.isoformat(),
            "is_canceled": appointment.is_canceled
        }
        for appointment in appointments
    ]

    return {"appointments": appointment_data}
