from typing import Optional
from hashlib import md5


def create_hash(to_hash: str, salt: Optional[str] = None) -> str:
    """helper function to hash strings"""
    if not salt:
        # [salt omitted]
        ...
    _hashed = md5((to_hash + salt).encode())
    return _hashed.hexdigest()
