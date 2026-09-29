"""
Authentication — JWT-based, backed by PostgreSQL.

Flow:
  1. User sends customer_id + password to /api/auth/login
  2. We verify against customer_repo (PostgreSQL)
  3. Fetch their roles from customer_roles table
  4. Issue a JWT containing: sub, name, roles, exp, iat
  5. Every subsequent request includes the JWT
  6. verify_token() decodes it — no DB call needed (stateless)

Production concerns:
  - Passwords verified via bcrypt (with demo shortcut)
  - Inactive accounts rejected
  - Roles baked into JWT so authorization checks need no DB call
  - Token expiry enforced
"""
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import jwt_config
from db.repositories.customer_repo import customer_repo

security_scheme = HTTPBearer()


async def create_token(customer_id: str, password: str = "demo") -> str:
    """
    Verify credentials against PostgreSQL and issue a JWT.
    Called by the /api/auth/login route.
    """
    # Step 1: Customer exists?
    customer = await customer_repo.get_by_id(customer_id)
    if not customer:
        raise HTTPException(status_code=401, detail="Unknown customer")

    # Step 2: Account active?
    if not customer["is_active"]:
        raise HTTPException(status_code=401, detail="Account is inactive")

    # Step 3: Password valid?
    is_valid = await customer_repo.verify_password(customer_id, password)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Step 4: Get roles from database
    roles = await customer_repo.get_roles(customer_id)

    # Step 5: Build and sign JWT
    payload = {
        "sub": customer_id,
        "name": customer["name"],
        "roles": roles,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=jwt_config.expiry_minutes),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, jwt_config.secret_key, algorithm=jwt_config.algorithm)


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> dict:
    """
    FastAPI dependency — extracts and validates the JWT.

    Usage in routes:
        @router.post("/chat")
        async def chat(user_claims: dict = Depends(verify_token)):
            customer_id = user_claims["sub"]
            roles = user_claims["roles"]

    This is SYNC — no database call needed. JWT is self-contained.
    """
    try:
        payload = jwt.decode(
            credentials.credentials,
            jwt_config.secret_key,
            algorithms=[jwt_config.algorithm],
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )