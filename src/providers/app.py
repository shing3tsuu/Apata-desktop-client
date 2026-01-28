import logging

from sqlalchemy.pool import StaticPool
from typing import AsyncIterable
from dishka import Provider, provide, Scope
from dishka import AsyncContainer, FromDishka
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.adapters.api.dao import CommonHTTPClient, AuthHTTPDAO, ContactHTTPDAO, MessageHTTPDAO, WebSocketDAO
from src.adapters.api.service import AuthHTTPService, ContactHTTPService, MessageHTTPService

from src.adapters.database.dao import (
    AbstractCommonDAO, CommonDAO,
    AbstractLocalUserDAO, LocalUserDAO,
    AbstractContactDAO, ContactDAO,
    AbstractMessageDAO, MessageDAO,
)

from src.adapters.database.service import LocalUserService, ContactService, MessageService
from src.adapters.database.structures import Base

from src.adapters.encryption.dao import (
    Abstract256Cipher, AES256GCMCipher,
    AbstractECDHCipher, X25519Cipher,
    AbstractECDSASignature, SECP256R1Signature,
    AbstractPasswordHasher, BcryptPasswordHasher,
)
from src.adapters.encryption.service import (
    EncryptionService,
    KeyManager
)
from src.adapters.encryption.storage import EncryptedKeyStorage

class AppProvider(Provider):
    def __init__(
            self,
            scope: Scope,
            logger: logging.Logger,
            iterations: int | None,
            symmetric_cipher: str,
            asymmetric_cipher: str,
            signature_cipher: str,
            base_url: str,
            verify_ssl: bool,
            base_ws_url: str
    ):
        super().__init__(scope=scope)
        self.logger = logger
        self.iterations = iterations
        self.symmetric_cipher = symmetric_cipher
        self.asymmetric_cipher = asymmetric_cipher
        self.signature_cipher = signature_cipher
        self.base_url = base_url
        self.verify_ssl = verify_ssl
        self.base_ws_url = base_ws_url

    # --- encryption and key management --- #

    @provide(scope=Scope.REQUEST)
    async def aes_cipher(self) -> Abstract256Cipher:
        if self.symmetric_cipher == "AESGCM":
            return AES256GCMCipher(logger=self.logger)
        # elif self.symmetric_cipher == "CHACHA20":
        #     return ChaCha20Poly1305Cipher(logger=self.logger) not implemented yet

    @provide(scope=Scope.REQUEST)
    async def ecdh_cipher(self) -> AbstractECDHCipher:
        if self.asymmetric_cipher == "X25519":
            return X25519Cipher(logger=self.logger)

    @provide(scope=Scope.REQUEST)
    async def ecdsa_signer(self) -> AbstractECDSASignature:
        if self.signature_cipher == "ECDSA-SECP256R1":
            return SECP256R1Signature(logger=self.logger)
        # maybe i will add ed25519, but nah

    @provide(scope=Scope.REQUEST)
    async def password_hasher(self) -> AbstractPasswordHasher:
        return BcryptPasswordHasher(logger=self.logger)

    @provide(scope=Scope.REQUEST)
    async def key_manager(self) -> KeyManager:
        if not self.iterations or not isinstance(self.iterations, int):
            self.iterations = 100000
        return KeyManager(iterations=self.iterations, logger=self.logger)

    @provide(scope=Scope.REQUEST)
    async def key_storage(self, key_manager: KeyManager) -> EncryptedKeyStorage:
        return EncryptedKeyStorage(
            key_manager=key_manager,
            logger=self.logger,
        )

    @provide(scope=Scope.REQUEST)
    async def encryption_service(
            self,
            aes_cipher: Abstract256Cipher,
            ecdh_cipher: AbstractECDHCipher,
            ecdsa_signer: AbstractECDSASignature
    ) -> EncryptionService:
        return EncryptionService(
            aes_cipher=aes_cipher,
            ecdh_cipher=ecdh_cipher,
            ecdsa_signer=ecdsa_signer,
            logger=self.logger
        )

    # --- http and websocket api --- #

    @provide(scope=Scope.APP)
    async def api_client(self) -> CommonHTTPClient:
        client = CommonHTTPClient(
            base_url=self.base_url,
            timeout=60.0,
            max_retries=3,
            retry_delay=1.0,
            verify=self.verify_ssl,
            logger=self.logger
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
    async def message_http_dao(self, http_client: CommonHTTPClient) -> MessageHTTPDAO:
        return MessageHTTPDAO(http_client=http_client)

    @provide(scope=Scope.APP)
    async def websocket_dao(self) -> WebSocketDAO:
        return WebSocketDAO(
            base_ws_url=self.base_ws_url,
            logger=self.logger,
            verify=self.verify_ssl
        )

    @provide(scope=Scope.REQUEST)
    async def auth_http_service(
            self,
            auth_dao: AuthHTTPDAO,
            encryption_service: EncryptionService
    ) -> AuthHTTPService:
        return AuthHTTPService(
            auth_dao=auth_dao,
            encryption_service=encryption_service
        )

    @provide(scope=Scope.REQUEST)
    async def contact_http_service(
            self,
            contact_dao: ContactHTTPDAO,
            auth_dao: AuthHTTPDAO,
            ecdsa_signer: AbstractECDSASignature,
    ) -> ContactHTTPService:
        return ContactHTTPService(
            contact_dao=contact_dao,
            auth_dao=auth_dao,
            ecdsa_signer=ecdsa_signer,
            logger=self.logger
        )

    @provide(scope=Scope.REQUEST)
    async def message_http_service(
            self,
            message_dao: MessageHTTPDAO,
            auth_dao: AuthHTTPDAO,
            encryption_service: EncryptionService,
            websocket_dao: WebSocketDAO
    ) -> MessageHTTPService:
        return MessageHTTPService(
            message_dao=message_dao,
            auth_dao=auth_dao,
            encryption_service=encryption_service,
            websocket_dao=websocket_dao,
            logger=self.logger
        )

    @provide(scope=Scope.APP)
    async def database(self) -> async_sessionmaker:
        try:
            database_url = "sqlite+aiosqlite:///apata.db"

            engine = create_async_engine(
                database_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool
            )

            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            logging.info("Database tables created successfully")

            return async_sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False
            )

        except Exception as e:
            logging.error(f"Failed to create database: {e}")
            raise

    @provide(scope=Scope.REQUEST)
    async def new_connection(self, sessionmaker: async_sessionmaker) -> AsyncIterable[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    @provide(scope=Scope.REQUEST)
    async def local_user_dao(self, session: AsyncSession) -> AbstractLocalUserDAO:
        return LocalUserDAO(session=session)

    @provide(scope=Scope.REQUEST)
    async def contact_dao(self, session: AsyncSession) -> AbstractContactDAO:
        return ContactDAO(session=session)

    @provide(scope=Scope.REQUEST)
    async def message_dao(self, session: AsyncSession) -> AbstractMessageDAO:
        return MessageDAO(session=session)

    @provide(scope=Scope.REQUEST)
    async def common_dao(self, session: AsyncSession) -> AbstractCommonDAO:
        return CommonDAO(session=session)

    @provide(scope=Scope.REQUEST)
    async def local_user_service(
            self,
            local_user_dao: AbstractLocalUserDAO,
            common_dao: AbstractCommonDAO
    ) -> LocalUserService:
        return LocalUserService(
            local_user_dao=local_user_dao,
            common_dao=common_dao,
            logger=self.logger
        )

    @provide(scope=Scope.REQUEST)
    async def contact_service(
            self,
            contact_dao: AbstractContactDAO,
            common_dao: AbstractCommonDAO
    ) -> ContactService:
        return ContactService(
            contact_dao=contact_dao,
            common_dao=common_dao,
            logger=self.logger
        )

    @provide(scope=Scope.REQUEST)
    async def message_service(
            self,
            message_dao: AbstractMessageDAO,
            common_dao: AbstractCommonDAO
    ) -> MessageService:
        return MessageService(
            message_dao=message_dao,
            common_dao=common_dao,
            logger=self.logger
        )