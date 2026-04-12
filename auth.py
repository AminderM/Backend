from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from models import User
from models_user import (
    UserRole, 
    normalize_role, 
    get_user_permissions, 
    has_permission,
    ROLE_MIGRATION_MAP,
    get_user_workspaces,
    has_workspace_access,
    Workspace
)
from database import db
import os

# JWT Configuration
SECRET_KEY = os.environ.get('JWT_SECRET', 'your-secret-key-change-this')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security
security = HTTPBearer()


def verify_password(plain_password, hashed_password):
    """Verify password against hash"""
    # Truncate password to 72 bytes for bcrypt compatibility
    if isinstance(plain_password, str):
        plain_password = plain_password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password):
    """Hash a password for storage"""
    # Truncate password to 72 bytes for bcrypt compatibility
    if isinstance(password, str):
        password = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return pwd_context.hash(password)


def create_access_token(data: dict):
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current authenticated user from JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if user is None:
        raise credentials_exception
    
    # Update last login time
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"last_login_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return User(**user)


# =============================================================================
# ROLE CHECKING HELPERS
# =============================================================================

def get_normalized_role(user: User) -> str:
    """Get user's normalized role (legacy roles mapped to new ones)"""
    role_value = user.role.value if hasattr(user.role, 'value') else str(user.role)
    return normalize_role(role_value)


def is_platform_admin(user: User) -> bool:
    """Check if user is a platform admin"""
    role = get_normalized_role(user)
    return role == "platform_admin"


def is_admin(user: User) -> bool:
    """Check if user is an admin (company admin) or platform admin"""
    role = get_normalized_role(user)
    return role in ["platform_admin", "admin"]


def is_manager_or_above(user: User) -> bool:
    """Check if user is manager or above"""
    role = get_normalized_role(user)
    return role in ["platform_admin", "admin", "manager"]


def is_dispatcher_or_above(user: User) -> bool:
    """Check if user has dispatcher level access or above"""
    role = get_normalized_role(user)
    return role in ["platform_admin", "admin", "manager", "dispatcher"]


def is_billing_user(user: User) -> bool:
    """Check if user has billing access"""
    role = get_normalized_role(user)
    return role in ["platform_admin", "admin", "billing"]


def is_driver(user: User) -> bool:
    """Check if user is a driver"""
    role = get_normalized_role(user)
    return role == "driver"


# =============================================================================
# ROLE-BASED DEPENDENCIES
# =============================================================================

def require_platform_admin(current_user: User = Depends(get_current_user)):
    """Dependency to require platform admin role"""
    if not is_platform_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin access required"
        )
    return current_user


def require_admin(current_user: User = Depends(get_current_user)):
    """Dependency to require admin role (platform or company admin)"""
    if not is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


def require_manager(current_user: User = Depends(get_current_user)):
    """Dependency to require manager role or above"""
    if not is_manager_or_above(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager access required"
        )
    return current_user


def require_dispatcher(current_user: User = Depends(get_current_user)):
    """Dependency to require dispatcher role or above"""
    if not is_dispatcher_or_above(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dispatcher access required"
        )
    return current_user


def require_billing(current_user: User = Depends(get_current_user)):
    """Dependency to require billing access"""
    if not is_billing_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Billing access required"
        )
    return current_user


def require_web_user(current_user: User = Depends(get_current_user)):
    """Dependency to restrict endpoint to website web tools users only."""
    role = get_normalized_role(current_user)
    portal = getattr(current_user, "portal", "tms")
    if role != "web_tools_user" or portal != "website":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: this endpoint is for website users only.",
        )
    return current_user


def require_tms_user(current_user: User = Depends(get_current_user)):
    """Dependency to block website users from TMS endpoints."""
    role = get_normalized_role(current_user)
    portal = getattr(current_user, "portal", "tms")
    if role == "web_tools_user" or portal == "website":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: this endpoint is not available for website users.",
        )
    return current_user


def require_role(allowed_roles: List[str]):
    """
    Factory function to create a dependency that requires specific roles
    Usage: Depends(require_role(["admin", "manager", "dispatcher"]))
    """
    async def role_checker(current_user: User = Depends(get_current_user)):
        role = get_normalized_role(current_user)
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(allowed_roles)}"
            )
        return current_user
    return role_checker


def require_permission(permission: str):
    """
    Factory function to create a dependency that requires a specific permission
    Usage: Depends(require_permission("manage_loads"))
    """
    async def permission_checker(current_user: User = Depends(get_current_user)):
        user_permissions = get_user_permissions(
            current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role),
            getattr(current_user, 'permissions', {})
        )
        if not user_permissions.get(permission, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}"
            )
        return current_user
    return permission_checker


# =============================================================================
# TENANT ISOLATION HELPERS
# =============================================================================

def check_tenant_access(user: User, resource_tenant_id: Optional[str]) -> bool:
    """
    Check if user has access to a resource based on tenant
    Platform admins can access all tenants
    Other users can only access their own tenant
    """
    if is_platform_admin(user):
        return True
    
    user_tenant_id = getattr(user, 'tenant_id', None) or getattr(user, 'company_id', None)
    return user_tenant_id == resource_tenant_id


def require_tenant_access(resource_tenant_id: str):
    """
    Dependency factory to check tenant access for a specific resource
    """
    async def tenant_checker(current_user: User = Depends(get_current_user)):
        if not check_tenant_access(current_user, resource_tenant_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Resource belongs to a different tenant"
            )
        return current_user
    return tenant_checker


# =============================================================================
# WORKSPACE ACCESS CONTROL
# =============================================================================

def require_workspace(workspace: str):
    """
    Dependency factory to check if user has access to a workspace
    Usage: Depends(require_workspace("dispatch"))
    """
    async def workspace_checker(current_user: User = Depends(get_current_user)):
        role = get_normalized_role(current_user)
        if not has_workspace_access(role, workspace):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: You don't have access to the {workspace} workspace"
            )
        return current_user
    return workspace_checker


def get_workspaces_for_user(user: User) -> List[str]:
    """Get list of workspaces a user can access"""
    role = get_normalized_role(user)
    return get_user_workspaces(role)

