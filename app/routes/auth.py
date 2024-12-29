from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.models import User
from app.schemas import UserCreate
from app.db import get_db
from pydantic import BaseModel
from fastapi_jwt_auth import AuthJWT
import traceback
from datetime import timedelta

from fastapi_jwt_auth.exceptions import AuthJWTException
from fastapi_jwt_auth.exceptions import JWTDecodeError

from fastapi.responses import JSONResponse


router = APIRouter()

from pydantic import BaseModel
from fastapi_jwt_auth import AuthJWT

# Define the configuration model
class Settings(BaseModel):
    authjwt_secret_key: str = "admin123" 
    authjwt_algorithm: str = "HS256"

# Load the configuration
@AuthJWT.load_config
def get_config():
    return Settings()
@router.get("/ok")
def okpost(Authorize: AuthJWT = Depends()
):
        

    try:
        Authorize.jwt_required()
        return {"message": "Token is valid"}
    except JWTDecodeError as e:
        traceback.print_exc()  
        return {"error": f"JWTDecodeError occurred: {e}"}
    except Exception as e:
        traceback.print_exc()
        return {"error": f"An unexpected error occurred: {e}"}


class LoginRequest(BaseModel):
    username: str
    password: str
@router.post("/register")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = User(username=user.username, password=user.password, role=user.role)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.post("/login")
def login_user(login_data: LoginRequest, db: Session = Depends(get_db), Authorize: AuthJWT = Depends()):
    # Fetch user by username
    user = db.query(User).filter(User.username == login_data.username).first()
    if not user or user.password != login_data.password:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    
    # Create JWT with user details
    access_token = Authorize.create_access_token(subject=user.id, user_claims={"role": user.role},expires_time=timedelta(hours=1))
    
    return {"access_token": access_token, "message": "Login successful", "role": user.role}

