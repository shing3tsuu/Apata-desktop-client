APATA - Encrypted Messenger

A secure, end-to-end encrypted messaging application built with Python and Flet, featuring military-grade encryption and a sleek terminal-style interface.

🛡️ Features Security & Encryption

    End-to-End Encryption using AES-256-GCM for message content

    Key Exchange via X25519 (ECDH) for perfect forward secrecy

    Digital Signatures using ECDSA (SECP384R1) for authentication

    Secure Key Storage with password-derived master key encryption

    Bcrypt Password Hashing with timing attack protection

Core Functionality

    Secure User Registration & Authentication

    Encrypted Message Exchange

    Contact Management

    Real-time Message Polling

    Message Delivery Status

    Session Management

Technical Features

    Async/Await Architecture for high performance
    
    SQLite Database with SQLAlchemy ORM
    
    Dependency Injection with Dishka
    
    RESTful API Client with retry logic (httpx)
    
    Modular Service Layer architecture
    
    Encryption Settings

    Key derivation iterations and algorithms can be configured in the respective service files. 🎯 Usage First Time Setup

Launch the application

    Enter your desired username and password

The system will automatically:

    Generate encryption key pairs

    Register with the messaging server

    Securely store your keys

    Establish an encrypted session

    Sending Messages
    
    Add contacts using their username
    
    Select a contact from your contact list
    
    Type your message and press send
    
    Messages are automatically encrypted before transmission

Security Features

    Automatic Key Rotation: Supports periodic key updates
    
    Forward Secrecy: Each session uses unique encryption keys
    
    Tamper Detection: Messages are authenticated and integrity-protected
    
    Secure Storage: Private keys are encrypted with your password

🛠️ Development Architecture Overview

    APATA follows a clean architecture pattern with clear separation of concerns:
    
    Presentation Layer: Flet-based UI components
    
    Application Layer: Business logic and use cases
    
    Domain Layer: Core entities and interfaces
    
    Infrastructure Layer: External concerns (API, database, encryption)
    
    Key Components Encryption Stack
    
    AESGCMCipher: AES-256-GCM for symmetric encryption
    
    X25519Cipher: Elliptic Curve Diffie-Hellman for key exchange
    
    SECP384R1Signature: ECDSA for digital signatures
    
    KeyManager: Secure key derivation and management

Data Persistence

    SQLAlchemy: Database ORM with async support
    
    Repository Pattern: Clean data access abstraction
    
    DTO Pattern: Data transfer objects for type safety
    
    API Communication
    
    CommonHTTPClient: Robust HTTP client with retry logic
    
    Service Layer: Business logic encapsulation
    
    Error Handling: Comprehensive exception hierarchy

Adding New Features

    New Message Types

    Extend Message model in structures.py

    Update encryption service handlers

    Add UI components in presentation layer

Additional Encryption

    Implement cipher interfaces

    Register new services in dependency container

    Update key management as needed

🔒 Security Model Cryptographic Protocols

    Key Exchange: X25519 ECDH
    
    Symmetric Encryption: AES-256-GCM
    
    Digital Signatures: ECDSA with SECP384R1
    
    Password Hashing: Bcrypt with configurable cost
    
    Key Management
    
    Master key derived from user password via PBKDF2
    
    Encryption keys stored in system keyring
    
    Session keys ephemeral for forward secrecy
    
    Threat Mitigation
    
    Timing Attacks: Constant-time password comparison
    
    Key Compromise: Support for key rotation
    
    Replay Attacks: Message timestamps and nonces
    
    MITM Attacks: Server-authenticated key exchange

🤝 Contributing

    We welcome contributions! Please see our Contributing Guidelines for details.
    
    Fork the repository
    
    Create a feature branch (git checkout -b feature/amazing-feature)
    
    Commit your changes (git commit -m 'Add amazing feature')
    
    Push to the branch (git push origin feature/amazing-feature)

    Open a Pull Requests

🚧 Roadmap

    Group messaging support
    
    File transfer encryption
    
    Voice/video call encryption
    
    Multi-device synchronization
    
    Offline message support
    
    Advanced contact management

⚠️ Disclaimer

    This is a beta version for educational and development purposes. Always conduct security audits before production use. The developers are not responsible for any security breaches resulting from misuse or misconfiguration.

🆘 Support

    For security issues, please contact the security team directly. For technical support, open an issue in the repository.
