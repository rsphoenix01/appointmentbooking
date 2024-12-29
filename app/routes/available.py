from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from fastapi_jwt_auth import AuthJWT
from pydantic import BaseModel

from app.models import Availability, User
from app.schemas import AvailabilityCreate
from app.db import get_db

router = APIRouter()

@router.post("/availability")
def create_availability(
    availability_data: AvailabilityCreate,
    db: Session = Depends(get_db),
    Authorize: AuthJWT = Depends()
):
    try:
        Authorize.jwt_required()

        user_id = int(Authorize.get_jwt_subject())
        raw_jwt = Authorize.get_raw_jwt()
        user_role = raw_jwt.get("role")

        if user_role != "professor":
            raise HTTPException(status_code=403, detail="Only professors are authorized to add availability")

        
        if availability_data.professor_id != user_id:
            raise HTTPException(status_code=403, detail="you cannot set availability for other professor!" )

        try:
            start_time = datetime.fromisoformat(availability_data.start_time)
            end_time = datetime.fromisoformat(availability_data.end_time)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {str(ve)}")

        if start_time >= end_time:
            raise HTTPException(status_code=400, detail="Start time should be before end time")

        overlapping_slots = db.query(Availability).filter(
            Availability.professor_id == user_id,
            (Availability.start_time < end_time) & (Availability.end_time > start_time)
        ).all()

        if overlapping_slots:
            conflict_details = [
                {"start_time": slot.start_time.isoformat(), "end_time": slot.end_time.isoformat()}
                for slot in overlapping_slots
            ]
            raise HTTPException(
                status_code=409,
                detail={"message": "Time slot conflicts found", "conflicts": conflict_details}
            )

        new_availability = Availability(
            professor_id=user_id,
            start_time=start_time,
            end_time=end_time
        )

        db.add(new_availability)
        db.commit()
        db.refresh(new_availability)

        return {
            "message": "Availability successfully added",
            "availability": {
                "id": new_availability.id,
                "start_time": new_availability.start_time,
                "end_time": new_availability.end_time,
                "professor_id": new_availability.professor_id
            }
        }

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=f"Invalid time format: {str(ve)}")
    except SQLAlchemyError as se:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(se)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

class ProfessorIdRequest(BaseModel):
    professor_id: int

@router.post("/getavailability")
def get_availability(
    request: ProfessorIdRequest,  
    Authorize: AuthJWT = Depends(),
    db: Session = Depends(get_db)
):
    
    Authorize.jwt_required()

    raw_jwt = Authorize.get_raw_jwt()
    user_role = raw_jwt.get("role")

    
    if user_role != "student":
        raise HTTPException(status_code=403, detail="Only students can view availability")

    
    professor_id = request.professor_id
    professor = db.query(User).filter(User.id == professor_id).first()

    if not professor:
        raise HTTPException(
            status_code=404, detail=f"No professor found for the id you have requested"
        )



    
    availability_slots = db.query(Availability).filter(
        Availability.professor_id == professor_id
    ).all()

    if not availability_slots:
        raise HTTPException(
            status_code=404, detail=f"No availability found for professor ID {professor_id}"
        )

    # Step 5: Format the availability data for the response
    availability_data = [
        {
            "availability_id": slot.id,
            "professor_id": slot.professor_id,
            "start_time": slot.start_time.isoformat(),
            "end_time": slot.end_time.isoformat(),
        }
        for slot in availability_slots
    ]

    return {"availability": availability_data}