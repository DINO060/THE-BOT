# ==================== src/utils/encryption.py ====================
"""Encryption utilities"""

from cryptography.fernet import Fernet
from src.core.config import settings


def get_cipher():
    """Get Fernet cipher instance"""
    return Fernet(settings.encryption_key.encode())


def encrypt_data(data: str) -> str:
    """Encrypt string data"""
    cipher = get_cipher()
    return cipher.encrypt(data.encode()).decode()


def decrypt_data(encrypted_data: str) -> str:
    """Decrypt string data"""
    cipher = get_cipher()
    return cipher.decrypt(encrypted_data.encode()).decode()
