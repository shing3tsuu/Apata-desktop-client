import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ContactStatusEnum(StrEnum):
    BLANK = "blank"
    PENDING_INCOMING = "pending(incoming)"
    PENDING_OUTGOING = "pending(outgoing)"
    ACCEPTED = "accepted"
    BLACKLIST = "blacklist"


class ChatEventTypeEnum(StrEnum):
    CREATED = "created"
    MEMBER_ADDED = "member_added"
    MEMBER_JOINED = "member_joined"
    MEMBER_LEFT = "member_left"
    MEMBER_REMOVED = "member_removed"
    NAME_CHANGED = "name_changed"


class MessageContentTypeEnum(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    ARCHIVE = "archive"
    CODE = "code"
    OTHER = "other"


class MessageContentMimeTypeEnum(StrEnum):
    # Text
    TEXT = ".txt"

    # Image
    JPEG = ".jpeg"
    PNG = ".png"
    GIF = ".gif"
    WEBP = ".webp"
    SVG = ".svg"
    BMP = ".bmp"
    TIFF = ".tiff"
    AVIF = ".avif"
    HEIC = ".heic"

    # Video
    MP4 = ".mp4"
    WEBM = ".webm"
    AVI = ".avi"
    MOV = ".mov"
    MKV = ".mkv"
    MPEG = ".mpeg"
    OGV = ".ogv"

    # Audio
    MP3 = ".mp3"
    WAV = ".wav"
    OGG = ".ogg"
    AAC = ".aac"
    M4A = ".m4a"
    OPUS = ".opus"
    FLAC = ".flac"

    # Document
    PDF = ".pdf"
    DOC = ".doc"
    DOCX = ".docx"
    XLS = ".xls"
    XLSX = ".xlsx"
    PPT = ".ppt"
    PPTX = ".pptx"

    # Archive
    ZIP = ".zip"
    RAR = ".rar"
    TAR = ".tar"
    GZIP = ".gz"
    SEVEN_Z = ".7z"

    # Code
    JSON = ".json"
    XML = ".xml"
    PYTHON = ".py"
    JS = ".js"
    HTML = ".html"
    CSS = ".css"

    # Other
    BINARY = ".bin"
    MARKDOWN = ".md"
    CSV = ".csv"


class LocalUser(Base):
    __tablename__ = "local_users"

    __table_args__ = (
        Index("ix_local_users_server_user_id", "server_user_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    server_user_id: Mapped[UUID]
    username: Mapped[str] = mapped_column(String(50))
    ed_public_key: Mapped[str] = mapped_column(Text)
    hashed_password: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[int | None] = mapped_column(default=0)

    contacts: Mapped[list["Contact"]] = relationship(
        "Contact", back_populates="user", cascade="all, delete-orphan"
    )

    owned_chats: Mapped[list["Chat"]] = relationship(
        "Chat", back_populates="owner", cascade="all, delete-orphan"
    )

    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="local_user", cascade="all, delete-orphan"
    )


class Contact(Base):
    __tablename__ = "contacts"

    __table_args__ = (
        Index("ix_contacts_server_user_id", "server_user_id"),
        UniqueConstraint("local_user_id", "server_user_id", name="uq_contact_user"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    local_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("local_users.id", ondelete="CASCADE")
    )
    server_user_id: Mapped[UUID]

    username: Mapped[str] = mapped_column(String(50))
    ed_public_key: Mapped[str] = mapped_column(Text)
    ecdh_public_key: Mapped[str] = mapped_column(Text)

    status: Mapped[ContactStatusEnum] = mapped_column(
        SAEnum(
            ContactStatusEnum,
            name="contactstatusenum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ContactStatusEnum.BLANK,
        server_default="blank",
    )

    online: Mapped[bool] = mapped_column(default=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime)

    user: Mapped["LocalUser"] = relationship("LocalUser", back_populates="contacts")

    chat_links: Mapped[list["ChatParticipant"]] = relationship(
        "ChatParticipant", back_populates="contact", cascade="all, delete-orphan"
    )

    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="contact", cascade="all, delete-orphan"
    )

    @property
    def chats(self) -> list["Chat"]:
        return [link.chat for link in self.chat_links]


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    server_chat_id: Mapped[UUID]
    server_owner_id: Mapped[UUID | None] = mapped_column(nullable=True)
    local_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("local_users.id", ondelete="CASCADE")
    )
    name: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    owner: Mapped["LocalUser"] = relationship("LocalUser", back_populates="owned_chats")

    participant_links: Mapped[list["ChatParticipant"]] = relationship(
        "ChatParticipant", back_populates="chat", cascade="all, delete-orphan"
    )

    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="chat", cascade="all, delete-orphan"
    )

    events: Mapped[list["ChatEvent"]] = relationship(
        "ChatEvent", back_populates="chat", cascade="all, delete-orphan"
    )

    @property
    def participants(self) -> list["Contact"]:
        return [link.contact for link in self.participant_links]


class ChatParticipant(Base):
    __tablename__ = "chat_participants"

    __table_args__ = (
        UniqueConstraint("chat_id", "contact_id", name="uq_chat_contact"),
    )

    chat_id: Mapped[UUID] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"),
        primary_key=True,
    )
    contact_id: Mapped[UUID] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(timezone.utc)
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    chat: Mapped["Chat"] = relationship("Chat", back_populates="participant_links")
    contact: Mapped["Contact"] = relationship("Contact", back_populates="chat_links")


class ChatEvent(Base):
    __tablename__ = "chat_events"

    __table_args__ = (
        Index("ix_chat_events_server_event_id", "server_event_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid7)

    chat_id: Mapped[UUID] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=True,
    )
    server_event_id: Mapped[UUID | None] = mapped_column(nullable=True)
    actor_server_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    target_server_user_id: Mapped[UUID | None] = mapped_column(nullable=True)

    event_type: Mapped[ChatEventTypeEnum] = mapped_column(
        SAEnum(
            ChatEventTypeEnum,
            name="chateventtypeenum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        )
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )

    chat: Mapped["Chat"] = relationship("Chat", back_populates="events")
    contact: Mapped["Contact"] = relationship("Contact")


class Message(Base):
    __tablename__ = "messages"

    __table_args__ = (
        Index("ix_messages_contact_timestamp", "contact_id", "timestamp"),
        Index("ix_messages_chat_timestamp", "chat_id", "timestamp"),
        Index("ix_messages_is_outgoing", "is_outgoing"),
        Index("ix_messages_is_delivered", "is_delivered"),
        Index("ix_messages_failed", "failed"),
        Index("ix_messages_timestamp", "timestamp"),
        CheckConstraint(
            "contact_id IS NOT NULL OR chat_id IS NOT NULL",
            name="message_contact_or_chat_required",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid7)

    local_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("local_users.id", ondelete="CASCADE")
    )
    server_message_id: Mapped[UUID]

    contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE")
    )
    chat_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE")
    )

    reply_to_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )

    content_type: Mapped[MessageContentTypeEnum] = mapped_column(
        SAEnum(
            MessageContentTypeEnum,
            name="messagecontenttypeenum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=MessageContentTypeEnum.TEXT,
        server_default="text",
    )

    content: Mapped[str | None] = mapped_column(Text)
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_content: Mapped[bytes | None] = mapped_column(LargeBinary)
    file_size: Mapped[int | None]
    file_mime_type: Mapped[MessageContentMimeTypeEnum] = mapped_column(
        SAEnum(
            MessageContentMimeTypeEnum,
            name="messagecontentmimetypeenum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=MessageContentMimeTypeEnum.TEXT,
        server_default=".txt",
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(timezone.utc)
    )
    is_outgoing: Mapped[bool]
    is_delivered: Mapped[bool] = mapped_column(default=False)
    failed: Mapped[bool | None] = mapped_column(nullable=True)

    local_user: Mapped["LocalUser"] = relationship(
        "LocalUser", back_populates="messages"
    )
    contact: Mapped[Optional["Contact"]] = relationship(
        "Contact", back_populates="messages"
    )
    chat: Mapped[Optional["Chat"]] = relationship("Chat", back_populates="messages")
    reply_to: Mapped[Optional["Message"]] = relationship(
        "Message", remote_side=[id], back_populates="replies"
    )
    replies: Mapped[list["Message"]] = relationship(
        "Message", back_populates="reply_to", cascade="all, delete-orphan"
    )
