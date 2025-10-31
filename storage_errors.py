"""
Custom exceptions for storage operations
"""


class StorageError(Exception):
    """Base exception for storage operations"""
    pass


class StorageIOError(StorageError):
    """Exception for file I/O errors"""
    pass


class StorageValidationError(StorageError):
    """Exception for validation errors"""
    pass


class StorageCorruptionError(StorageError):
    """Exception for data corruption"""
    pass


class StorageLockError(StorageError):
    """Exception for locking/concurrency errors"""
    pass


class StorageIDCollisionError(StorageError):
    """Exception for ID collision"""
    pass
