from passlib.context import CryptContext

_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_passcode(plain: str) -> str:
    return _ctx.hash(plain)


def verify_passcode(plain: str, hashed: str) -> bool:
    return _ctx.verify(plain, hashed)
