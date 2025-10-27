# APATA - Encrypted Messenger

A secure, end-to-end encrypted desktop messaging application built with Python and Flet, featuring military-grade encryption and a sleek terminal-style interface.

## 🛡️ Core Features

### Security & Encryption
- **End-to-End Encryption** using AES-256-GCM for message content
- **Key Exchange** via X25519 (ECDH) for perfect forward secrecy for every session
- **Digital Signatures** using ECDSA (SECP384R1) for authentication (challenge-response)
- **Secure Key Storage** with password-derived master key encryption (keyring, pbkdf2 (600000 itetations))
- **Bcrypt Password Hashing** with timing attack protection (12 rounds)

### Application Functionality
- **Secure User Registration & Authentication**
- **Encrypted Message Exchange**
- **Contact Management** (add, search, accept, reject, pending requests)
- **Real-time Message Polling** (long polling + postgresq listen/notify)
- **Message Delivery Status**
- **Session Management**

### User Interface
- **Terminal-style Interface** (black, white, grey and cyan colors)
- **Multiple Screens**: Login, Loading, Messenger, Contacts and others
- **Responsive Design** with 960x720 window size
- **Real-time Status Updates**

## 🏗️ Architecture & Technologies

### Architecture Pattern
- **Clean Architecture** with clear separation of concerns
- **Dependency Injection** using Dishka framework
- **Async/Await** throughout the application

### Technology Stack
- **Frontend**: Flet (Python UI framework)
- **HTTP Client**: httpx with retry logic and timeout handling
- **Database**: SQLite with SQLAlchemy Async ORM
- **Cryptography**: cryptography.hazmat primitives (AES, ECDH, ECDSA, SHA-2, PBKDF2, bcrypt)
- **Dependency Management**: Dishka IoC container

### Encryption Layer
- `AESGCMCipher`: AES-256-GCM symmetric encryption
- `X25519Cipher`: Elliptic Curve Diffie-Hellman key exchange
- `SECP384R1Signature`: ECDSA digital signatures
- `EncryptionService`: Orchestrates message encryption/decryption
- `KeyManager`: Secure key derivation and management

### Service Layer

httpx layers:
- `AuthHTTPDAO/Service`: Handles user registration and authentication
- `MessageHTTPDAO/Service`: Manages encrypted message exchange
- `ContactHTTPDAO/Service`: Handles contact management
- `EncryptionService`: Coordinates cryptographic operations

sqlalchemy layers:
- `LocalUserDAO/Service`: Stores local user data (multi-user support available)
- `ContactDAO/Service`: Local storage of users contacts
- `MessageDAO/Service`: Local storage of all users messages in encrypted form (kek from password via aes)
- 'DTO': pydantic models for convenient work with the database, validation and serialization

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- Dependencies: flet, httpx, sqlalchemy, pydantic, cryptography, dishka

### Installation
1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Run the application: `python main.py`

### First Time Setup
1. Launch the application
2. Enter username and password on login screen
3. System automatically generates encryption keys
4. Proceeds to contact management and messaging interface

## 🔒 Security Model

### Cryptographic Protocols
- **Key Exchange**: X25519 ECDH
- **Symmetric Encryption**: AES-256-GCM
- **Digital Signatures**: ECDSA with SECP384R1
- **Password Hashing**: Bcrypt

### Key Management
- Master key derived from user password via PBKDF2
- Private keys stored encrypted in local database
- Session keys ephemeral for forward secrecy

### Threat Mitigation
- Timing attack protection in password comparison
- Support for key rotation
- Message authentication and integrity protection

## 📱 UI/UX Overview

### Screens Flow
1. **Login**: Terminal-style authentication
2. **Loading**: System initialization with progress indicators
3. **Messenger**: Main chat interface with contact list
4. **Contacts**: Contact management and search

### Design Features
- Retro terminal aesthetic with green/black color scheme
- Real-time status indicators
- Secure connection establishment visual feedback
- Contact presence indicators (online/offline/last seen)

## 🛠️ Development

### Adding Features
- **New Message Types**: Extend Message model in structures.py
- **Additional Encryption**: Implement cipher interfaces
- **UI Components**: Add to presentation/pages directory

### Testing
- Encryption tests for all cryptographic components
- API integration tests
- Database operation tests

## ⚠️ Disclaimer

This is a beta version for educational and development purposes. Always conduct security audits before production use. The developers are not responsible for any security breaches resulting from misuse or misconfiguration.

## 🆘 Support

For security issues, please contact the security team directly. For technical support, open an issue in the repository.

---

**APATA ENCRYPTED SYSTEMS VER 0.1 BETA**
