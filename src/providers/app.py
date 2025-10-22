import logging
from venv import logger

from sqlalchemy.pool import StaticPool
from typing import AsyncIterable
from dishka import Provider, provide, Scope
from dishka import AsyncContainer, FromDishka
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.adapters.api.dao import CommonHTTPClient, AuthHTTPDAO, ContactHTTPDAO, MessageHTTPDAO
from src.adapters.api.service import AuthHTTPService, ContactHTTPService, MessageHTTPService, EncryptionService

from src.adapters.database.dao import (
    AbstractCommonDAO, CommonDAO,
    AbstractLocalUserDAO, LocalUserDAO,
    AbstractContactDAO, ContactDAO,
    AbstractMessageDAO, MessageDAO,
)

from src.adapters.database.service import LocalUserService, ContactService, MessageService
from src.adapters.database.structures import Base

from src.adapters.encryption.service import (
    AbstractAES256Cipher, AESGCMCipher,
    AbstractECDHCipher, X25519Cipher,
    AbstractECDSASignature, SECP384R1Signature,
    AbstractPasswordHasher, BcryptPasswordHasher,
    KeyManager
)
from src.adapters.encryption.storage import EncryptedKeyStorage

class AppProvider(Provider):
    scope = Scope.APP
    @provide(scope=Scope.REQUEST)
    async def logger(self) -> logging.Logger:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        )
        return logging.getLogger(__name__)

    @provide(scope=Scope.REQUEST)
    async def aes_cipher(self, logger: logging.Logger) -> AbstractAES256Cipher:
        return AESGCMCipher(logger=logger)

    @provide(scope=Scope.REQUEST)
    async def ecdh_cipher(self, logger: logging.Logger) -> AbstractECDHCipher:
        return X25519Cipher(logger=logger)

    @provide(scope=Scope.REQUEST)
    async def ecdsa_signer(self, logger: logging.Logger) -> AbstractECDSASignature:
        return SECP384R1Signature(logger=logger)

    @provide(scope=Scope.REQUEST)
    async def password_hasher(self, logger: logging.Logger) -> AbstractPasswordHasher:
        return BcryptPasswordHasher(logger=logger)

    @provide(scope=Scope.REQUEST)
    async def key_manager(self, logger: logging.Logger) -> KeyManager:
        return KeyManager(iterations=600000, logger=logger)

    @provide(scope=Scope.REQUEST)
    async def key_storage(self, key_manager: KeyManager, logger: logging.Logger) -> EncryptedKeyStorage:
        return EncryptedKeyStorage(
            key_manager=key_manager,
            logger=logger,
        )

    @provide(scope=Scope.APP)
    async def api_client(self) -> CommonHTTPClient:
        client = CommonHTTPClient(
            base_url="http://127.0.0.1:8000/",
            timeout=60.0,
            max_retries=3,
            retry_delay=1.0,
            logger=logger
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

    @provide(scope=Scope.REQUEST)
    async def auth_http_service(
            self,
            auth_dao: AuthHTTPDAO,
            ecdsa_signer: AbstractECDSASignature,
            ecdh_cipher: AbstractECDHCipher
    ) -> AuthHTTPService:
        return AuthHTTPService(
            auth_dao=auth_dao,
            ecdsa_signer=ecdsa_signer,
            ecdh_cipher=ecdh_cipher
        )

    @provide(scope=Scope.REQUEST)
    async def contact_http_service(
            self,
            contact_dao: ContactHTTPDAO,
            auth_dao: AuthHTTPDAO,
            logger: logging.Logger
    ) -> ContactHTTPService:
        return ContactHTTPService(
            contact_dao=contact_dao,
            auth_dao=auth_dao,
            logger=logger
        )

    @provide(scope=Scope.REQUEST)
    async def message_http_service(
            self,
            message_dao: MessageHTTPDAO,
            auth_dao: AuthHTTPDAO,
            encryption_service: EncryptionService,
            logger: logging.Logger
    ) -> MessageHTTPService:
        return MessageHTTPService(
            message_dao=message_dao,
            auth_dao=auth_dao,
            encryption_service=encryption_service,
            logger=logger
        )

    @provide(scope=Scope.REQUEST)
    async def encryption_service(
            self,
            ecdh_cipher: AbstractECDHCipher,
            aes_cipher: AbstractAES256Cipher,
            logger: logging.Logger
    ) -> EncryptionService:
        return EncryptionService(
            ecdh_cipher=ecdh_cipher,
            aes_cipher=aes_cipher,
            logger=logger
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
            common_dao=common_dao
        )

    @provide(scope=Scope.REQUEST)
    async def contact_service(
            self,
            contact_dao: AbstractContactDAO,
            common_dao: AbstractCommonDAO
    ) -> ContactService:
        return ContactService(
            contact_dao=contact_dao,
            common_dao=common_dao
        )

    @provide(scope=Scope.REQUEST)
    async def message_service(
            self,
            message_dao: AbstractMessageDAO,
            common_dao: AbstractCommonDAO,
    ) -> MessageService:
        return MessageService(
            message_dao=message_dao,
            common_dao=common_dao
        )