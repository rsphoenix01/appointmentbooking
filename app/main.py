from fastapi import FastAPI

from app.routes import auth, available, appointments
from app.db import Base, engine
import sqlite3

Base.metadata.create_all(bind=engine)

application = FastAPI()


application.include_router(auth.router)
application.include_router(available.router)
application.include_router(appointments.router)




