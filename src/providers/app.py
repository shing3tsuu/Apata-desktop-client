import logging
from typing import AsyncIterable

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.adapters.api.dao import (
    AuthHTTPDAO,
    ChatHTTPDAO,
    CommonHTTPClient,
    ContactHTTPDAO,
    FileHTTPDAO,
    MessageHTTPDAO,
    WebSocketDAO,
)
from src.adapters.api.service import (
    AuthHTTPService,
    ChatHTTPService,
    ContactHTTPService,
    FileHTTPService,
    FileStorageState,
    MessageHTTPService,
    WebSocketService,
)
from src.adapters.database.dao import (
    AbstractChatDAO,
    AbstractCommonDAO,
    AbstractContactDAO,
    AbstractLocalUserDAO,
    AbstractMessageDAO,
    ChatDAO,
    CommonDAO,
    ContactDAO,
    LocalUserDAO,
    MessageDAO,
)
from src.adapters.database.service import (
    ChatService,
    ContactService,
    LocalUserService,
    MessageService,
)
from src.adapters.database.structures import Base
from src.adapters.encryption.dao import (
    Abstract256Cipher,
    AbstractECDHCipher,
    AbstractEDSignature,
    AbstractPasswordHasher,
    AES256GCMCipher,
    AES256GCMSIVCipher,
    Argon2PasswordHasher,
    BcryptPasswordHasher,
    Ed25519Signature,
    SECP256R1Signature,
    X25519Cipher,
)
from src.adapters.encryption.service import EncryptionService, KeyManager
from src.adapters.encryption.storage import EncryptedKeyStorage

from .state import AppState


class StateProvider(Provider):
    app_state = provide(AppState, scope=Scope.APP)

class AppProvider(Provider):
    def __init__(
        self,
        scope: Scope,
        logger: logging.Logger,
        symmetric_cipher: str,
        asymmetric_cipher: str,
        signature_cipher: str,
        password_cipher: str,
        base_url: str,
        verify_ssl: bool,
        base_ws_url: str,
    ):
        super().__init__(scope=scope)
        self.logger = logger
        self.symmetric_cipher = symmetric_cipher
        self.asymmetric_cipher = asymmetric_cipher
        self.signature_cipher = signature_cipher
        self.password_cipher = password_cipher
        self.base_url = base_url
        self.verify_ssl = verify_ssl
        self.base_ws_url = base_ws_url

    @provide(scope=Scope.APP)
    async def aes_cipher(self) -> Abstract256Cipher:
        if self.symmetric_cipher == "AESGCM":
            return AES256GCMCipher()
        # elif self.symmetric_cipher == "CHACHA20":
        #     return ChaCha20Poly1305Cipher(logger=self.logger) not implemented yet
        elif self.symmetric_cipher == "AESGCMSIV":
            return AES256GCMSIVCipher()
        raise ValueError(f"Unsupported symmetric cipher: {self.symmetric_cipher}")

    @provide(scope=Scope.APP)
    async def ecdh_cipher(self) -> AbstractECDHCipher:
        if self.asymmetric_cipher == "X25519":
            return X25519Cipher()
        raise ValueError(f"Unsupported asymmetric cipher: {self.asymmetric_cipher}")

    @provide(scope=Scope.APP)
    async def ed_signer(self) -> AbstractEDSignature:
        if self.signature_cipher == "ECDSA-SECP256R1":
            return SECP256R1Signature()
        if self.signature_cipher == "ED-25519":
            return Ed25519Signature()
        raise ValueError(f"Unsupported signature cipher: {self.signature_cipher}")

    @provide(scope=Scope.REQUEST)
    async def password_hasher(self) -> AbstractPasswordHasher:
        if self.password_cipher == "BCRYPT":
            return BcryptPasswordHasher()
        if self.password_cipher == "ARGON2":
            return Argon2PasswordHasher()
        raise ValueError(f"Unsupported password cipher: {self.password_cipher}")

    @provide(scope=Scope.REQUEST)
    async def key_manager(self) -> KeyManager:
        return KeyManager(iterations=100000, logger=self.logger)

    @provide(scope=Scope.REQUEST)
    async def key_storage(self, key_manager: KeyManager) -> EncryptedKeyStorage:
        return EncryptedKeyStorage(
            key_manager=key_manager,
            logger=self.logger,
        )

    @provide(scope=Scope.APP)
    async def encryption_service(
        self,
        aes_cipher: Abstract256Cipher,
        ecdh_cipher: AbstractECDHCipher,
        ed_signer: AbstractEDSignature,
    ) -> EncryptionService:
        return EncryptionService(
            aes_cipher=aes_cipher,
            ecdh_cipher=ecdh_cipher,
            ed_signer=ed_signer,
            logger=self.logger,
        )

    @provide(scope=Scope.APP)
    async def api_client(self) -> CommonHTTPClient:
        client = CommonHTTPClient(
            base_url=self.base_url,
            timeout=60.0,
            max_retries=3,
            retry_delay=1.0,
            verify=self.verify_ssl,
            logger=self.logger,
        )
        await client.__aenter__()
        return client

    @provide(scope=Scope.REQUEST)
    async def auth_http_dao(self, http_client: CommonHTTPClient) -> AuthHTTPDAO:
        return AuthHTTPDAO(http_client=http_client)

    @provide(scope=Scope.REQUEST)
    async def contact_http_dao(self, http_client: CommonHTTPClient) -> ContactHTTPDAO:
        return ContactHTTPDAO(http_client=http_client)

    @provide(scope=Scope.REQUEST)
    async def chat_http_dao(self, http_client: CommonHTTPClient) -> ChatHTTPDAO:
        return ChatHTTPDAO(http_client=http_client)

    @provide(scope=Scope.REQUEST)
    async def file_http_dao(self, http_client: CommonHTTPClient) -> FileHTTPDAO:
        return FileHTTPDAO(http_client=http_client)

    @provide(scope=Scope.REQUEST)
    async def message_http_dao(self, http_client: CommonHTTPClient) -> MessageHTTPDAO:
        return MessageHTTPDAO(http_client=http_client)

    @provide(scope=Scope.APP)
    async def websocket_dao(self) -> WebSocketDAO:
        return WebSocketDAO(
            base_ws_url=self.base_ws_url, logger=self.logger, verify=self.verify_ssl
        )

    @provide(scope=Scope.REQUEST)
    async def auth_http_service(
        self, auth_dao: AuthHTTPDAO, encryption_service: EncryptionService
    ) -> AuthHTTPService:
        return AuthHTTPService(auth_dao=auth_dao, encryption_service=encryption_service)

    @provide(scope=Scope.REQUEST)
    async def contact_http_service(
        self,
        contact_dao: ContactHTTPDAO,
        auth_dao: AuthHTTPDAO,
        encryption_service: EncryptionService,
    ) -> ContactHTTPService:
        return ContactHTTPService(
            contact_dao=contact_dao,
            auth_dao=auth_dao,
            encryption_service=encryption_service,
            logger=self.logger,
        )

    @provide(scope=Scope.REQUEST)
    async def chat_http_service(self, chat_dao: ChatHTTPDAO) -> ChatHTTPService:
        return ChatHTTPService(chat_dao=chat_dao)

    @provide(scope=Scope.REQUEST)
    async def message_http_service(
        self,
        message_dao: MessageHTTPDAO,
        auth_dao: AuthHTTPDAO,
        encryption_service: EncryptionService,
    ) -> MessageHTTPService:
        return MessageHTTPService(
            message_dao=message_dao,
            auth_dao=auth_dao,
            encryption_service=encryption_service,
            logger=self.logger,
        )

    @provide(scope=Scope.APP)
    async def file_storage_state(self) -> FileStorageState:
        return FileStorageState()

    @provide(scope=Scope.REQUEST)
    async def file_http_service(
        self,
        file_dao: FileHTTPDAO,
        auth_dao: AuthHTTPDAO,
        encryption_service: EncryptionService,
    ) -> FileHTTPService:
        return FileHTTPService(
            file_dao=file_dao,
            auth_dao=auth_dao,
            encryption_service=encryption_service,
            logger=self.logger,
        )

    @provide(scope=Scope.APP)
    async def websocket_service(
        self,
        websocket_dao: WebSocketDAO,
    ) -> WebSocketService:
        return WebSocketService(
            websocket_dao=websocket_dao,
            logger=self.logger,
        )

    @provide(scope=Scope.APP)
    async def database(self) -> async_sessionmaker:
        try:
            database_url = "sqlite+aiosqlite:///apata.db"

            engine = create_async_engine(
                database_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )

            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            logging.info("Database tables created successfully")

            return async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
            )

        except Exception as e:
            logging.error(f"Failed to create database: {e}")
            raise

    @provide(scope=Scope.REQUEST)
    async def new_connection(
        self, sessionmaker: async_sessionmaker
    ) -> AsyncIterable[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    @provide(scope=Scope.REQUEST)
    async def local_user_dao(self, session: AsyncSession) -> AbstractLocalUserDAO:
        return LocalUserDAO(session=session)

    @provide(scope=Scope.REQUEST)
    async def contact_dao(self, session: AsyncSession) -> AbstractContactDAO:
        return ContactDAO(session=session)

    @provide(scope=Scope.REQUEST)
    async def chat_dao(self, session: AsyncSession) -> AbstractChatDAO:
        return ChatDAO(session=session)

    @provide(scope=Scope.REQUEST)
    async def message_dao(self, session: AsyncSession) -> AbstractMessageDAO:
        return MessageDAO(session=session)

    @provide(scope=Scope.REQUEST)
    async def common_dao(self, session: AsyncSession) -> AbstractCommonDAO:
        return CommonDAO(session=session)

    @provide(scope=Scope.REQUEST)
    async def local_user_service(
        self, local_user_dao: AbstractLocalUserDAO, common_dao: AbstractCommonDAO
    ) -> LocalUserService:
        return LocalUserService(local_user_dao=local_user_dao, common_dao=common_dao)

    @provide(scope=Scope.REQUEST)
    async def contact_service(
        self, contact_dao: AbstractContactDAO, common_dao: AbstractCommonDAO
    ) -> ContactService:
        return ContactService(
            contact_dao=contact_dao, common_dao=common_dao, logger=self.logger
        )

    @provide(scope=Scope.REQUEST)
    async def chat_service(
        self, chat_dao: AbstractChatDAO, common_dao: AbstractCommonDAO
    ) -> ChatService:
        return ChatService(chat_dao=chat_dao, common_dao=common_dao, logger=self.logger)

    @provide(scope=Scope.REQUEST)
    async def message_service(
        self,
        message_dao: AbstractMessageDAO,
        common_dao: AbstractCommonDAO,
        aes_cipher: Abstract256Cipher,
    ) -> MessageService:
        return MessageService(
            message_dao=message_dao,
            common_dao=common_dao,
            aes_cipher=aes_cipher,
            logger=self.logger,
        )
