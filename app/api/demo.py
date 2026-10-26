"""Explicit local-demo account switching; uses the existing session mechanism."""
from fastapi import APIRouter,HTTPException,Request,Response
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select
from app.dependencies import Db,Config,check_origin
from app.models.user import User
from app.repositories.auth import user_by_email
from app.services.auth import rate_limit
from app.api.auth import sign_in
from app.schemas.auth import AuthResponse
from app.seed import SCENARIOS

router=APIRouter(prefix='/api/demo',tags=['Synthetic demo'])


@router.get('/scenarios')
async def scenarios(db:Db,settings:Config):
    if not settings.demo_auth_enabled:raise HTTPException(404)
    result=[]
    for key,title,options in SCENARIOS:
        user=await user_by_email(db,key+'@demo.example.com')
        if user and user.is_demo:result.append({'key':key,'title':title,'email':user.email})
    employee=await user_by_email(db,'employee@demo.example.com')
    if employee and employee.is_demo:result.append({'key':'employee','title':'Сотрудник без права подписи','email':employee.email})
    return result


class DemoChoice(BaseModel):
    model_config=ConfigDict(extra='forbid')
    key:str=Field(max_length=40)


@router.post('/login',response_model=AuthResponse)
async def demo_login(body:DemoChoice,request:Request,response:Response,db:Db,settings:Config):
    check_origin(request)
    if not settings.demo_auth_enabled:raise HTTPException(404)
    await rate_limit(db,request,settings)
    if body.key not in {k for k,_,_ in SCENARIOS}|{'employee'}:raise HTTPException(404)
    user=await user_by_email(db,body.key+'@demo.example.com')
    if not user or not user.is_demo:raise HTTPException(404,'Синтетический аккаунт не подготовлен')
    return await sign_in(db,user,request,response,settings)
