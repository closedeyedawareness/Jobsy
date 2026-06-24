from pydantic import BaseModel
class Job(BaseModel):
    job_id:str
    title:str
