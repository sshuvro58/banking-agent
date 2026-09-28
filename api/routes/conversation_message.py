# routes/conversation_message.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from database import get_db
from models import ConversationMessage
from schemas import ConversationMessageCreate, ConversationMessageOut, ConversationMessageUpdate

router = APIRouter(prefix="/conversation-message", tags=["conversation-messages"])


@router.get("/get_all", response_model=list[ConversationMessageOut])
def list_conversation_messages(db: DBSession = Depends(get_db)):
    print("Calling list_conversation_messages")
    return db.query(ConversationMessage).all()


@router.get("/get/{message_id}", response_model=ConversationMessageOut)
def get_conversation_message(message_id: int, db: DBSession = Depends(get_db)):
    print("Calling get_conversation_message")
    message = db.get(ConversationMessage, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Conversation message not found")
    return message


@router.post("/create", response_model=ConversationMessageOut, status_code=201)
def create_conversation_message(payload: ConversationMessageCreate, db: DBSession = Depends(get_db)):
    print("Calling create_conversation_message")
    message = ConversationMessage(**payload.model_dump())
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.patch("/update/{message_id}", response_model=ConversationMessageOut)
def update_conversation_message(
    message_id: int, payload: ConversationMessageUpdate, db: DBSession = Depends(get_db)
):
    print("Calling update_conversation_message")
    message = db.get(ConversationMessage, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Conversation message not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(message, field, value)
    db.commit()
    db.refresh(message)
    return message


@router.delete("/delete/{message_id}", status_code=204)
def delete_conversation_message(message_id: int, db: DBSession = Depends(get_db)):
    print("Calling delete_conversation_message")
    message = db.get(ConversationMessage, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="Conversation message not found")
    db.delete(message)
    db.commit()
