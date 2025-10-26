from sqlalchemy import ForeignKey, String, Text, DateTime, Boolean, Index, BigInteger, LargeBinary
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from datetime import datetime
from typing import List, Optional

class Base(DeclarativeBase):
    pass

class LocalUser(Base):
    __tablename__ = "local_users"

    __table_args__ = (
        Index('ix_local_users_server_user_id', 'server_user_id', unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    server_user_id: Mapped[int] = mapped_column(BigInteger)
    username: Mapped[str] = mapped_column(String(50))
    hashed_password: Mapped[str] = mapped_column(String(100), nullable=False)

    # Исправленные отношения
    contacts: Mapped[List["Contact"]] = relationship(
        "Contact",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="local_user",
        cascade="all, delete-orphan"
    )


class Contact(Base):
    __tablename__ = "contacts"

    __table_args__ = (
        Index('ix_contacts_server_user_id', 'server_user_id'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    local_user_id: Mapped[int] = mapped_column(ForeignKey("local_users.id", ondelete="CASCADE"))
    server_user_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[Optional[str]] = mapped_column(String(50))
    username: Mapped[str] = mapped_column(String(50))
    ecdh_public_key: Mapped[str] = mapped_column(Text)
    last_seen: Mapped[Optional[datetime]]

    user: Mapped["LocalUser"] = relationship(
        "LocalUser",
        back_populates="contacts"
    )

    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="contact",
        cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    __table_args__ = (
        Index('ix_messages_contact_timestamp', 'contact_id', 'timestamp'),
        Index('ix_messages_server_message_id', 'server_message_id', unique=True),
        Index('ix_messages_is_outgoing', 'is_outgoing'),
        Index('ix_messages_is_delivered', 'is_delivered'),
        Index('ix_messages_timestamp', 'timestamp'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    local_user_id: Mapped[int] = mapped_column(ForeignKey("local_users.id", ondelete="CASCADE"))
    server_message_id: Mapped[int]
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    type: Mapped[str] = mapped_column(String(20))
    is_outgoing: Mapped[bool]
    is_delivered: Mapped[bool] = mapped_column(default=False)

    # Исправленные отношения
    contact: Mapped["Contact"] = relationship(
        "Contact",
        back_populates="messages"
    )

    local_user: Mapped["LocalUser"] = relationship(
        "LocalUser",
        back_populates="messages"
    )