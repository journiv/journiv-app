"""
User service for handling users and user settings.
"""
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select
from app.core.config import settings

from app.core.exceptions import (
    UserNotFoundError,
    UserAlreadyExistsError,
    InvalidCredentialsError,
    UnauthorizedError,
    UserSettingsNotFoundError,
)
from app.core.logging_config import log_error, log_warning, log_info
from app.core.security import get_password_hash, verify_password, create_access_token, create_refresh_token
from app.models.user import User, UserSettings
from app.models.external_identity import ExternalIdentity
from app.models.enums import UserRole
from app.schemas.user import UserCreate, UserUpdate, UserSettingsCreate, UserSettingsUpdate, AdminUserCreate, AdminUserUpdate

# Hash evaluated once to keep timing consistent for missing users
_DUMMY_PASSWORD_HASH = get_password_hash("journiv-dummy-password")


def _schema_dump(schema_obj, *, exclude_unset: bool = False):
    """Support both Pydantic v1 and v2 dump APIs."""
    if hasattr(schema_obj, "model_dump"):
        return schema_obj.model_dump(exclude_unset=exclude_unset)
    return schema_obj.dict(exclude_unset=exclude_unset)


class UserService:
    """User service class."""

    def __init__(self, session: Session):
        self.session = session

    def is_first_user(self) -> bool:
        """
        Check if this is the first user (database has zero users).
        Uses SELECT FOR UPDATE to prevent race conditions.

        Returns:
            bool: True if this is the first user, False otherwise
        """
        from sqlalchemy import func, text

        # Use SELECT COUNT(*) FOR UPDATE to lock the table and prevent race conditions
        # This ensures that concurrent user creations will be serialized
        try:
            # For SQLite, we can't use FOR UPDATE, so we just count
            # For PostgreSQL, we use FOR UPDATE to lock
            if 'sqlite' in str(self.session.bind.url).lower():
                count = self.session.exec(select(func.count(User.id))).one()
                return count == 0
            else:
                statement = select(User.id).limit(1).with_for_update()
                result = self.session.exec(statement).first()
                return result is None
        except Exception as exc:
            log_error(exc, context="is_first_user check")
            return False

    def count_admin_users(self) -> int:
        """Count the number of admin users."""
        from sqlalchemy import func
        return self.session.exec(
            select(func.count(User.id)).where(User.role == UserRole.ADMIN)
        ).one()

    def can_delete_user(self, user_id: str) -> tuple[bool, Optional[str]]:
        """
        Check if a user can be deleted.

        Args:
            user_id: User ID to check

        Returns:
            tuple: (can_delete: bool, error_message: Optional[str])
        """
        user = self.get_user_by_id(user_id)
        if not user:
            return False, "User not found"

        # Cannot delete the last admin
        if user.role == UserRole.ADMIN:
            admin_count = self.count_admin_users()
            if admin_count <= 1:
                return False, "Cannot delete the last admin user. At least one admin must exist."

        return True, None

    def can_update_user_role(self, user_id: str, new_role: UserRole) -> tuple[bool, Optional[str]]:
        """
        Check if a user's role can be updated.

        Args:
            user_id: User ID to check
            new_role: New role to assign

        Returns:
            tuple: (can_update: bool, error_message: Optional[str])
        """
        user = self.get_user_by_id(user_id)
        if not user:
            return False, "User not found"

        # If demoting from admin to user, check if this is the last admin
        if user.role == UserRole.ADMIN and new_role != UserRole.ADMIN:
            admin_count = self.count_admin_users()
            if admin_count <= 1:
                return False, "Cannot demote the last admin user. At least one admin must exist."

        return True, None

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        try:
            user_uuid = uuid.UUID(user_id)
            statement = select(User).where(User.id == user_uuid)
            return self.session.exec(statement).first()
        except ValueError:
            return None

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        statement = select(User).where(User.email == email)
        return self.session.exec(statement).first()

    def is_oidc_user(self, user_id: str) -> bool:
        """Check if user is an OIDC user by checking for ExternalIdentity."""
        try:
            user_uuid = uuid.UUID(user_id)
            statement = select(ExternalIdentity).where(ExternalIdentity.user_id == user_uuid)
            external_identity = self.session.exec(statement).first()
            return external_identity is not None
        except ValueError:
            return False

    def is_signup_disabled(self) -> bool:
        """Check if signup is disabled from app settings.
        Returns:
            bool: True if signup is disabled, False otherwise.
        """
        return settings.disable_signup

    def create_user(self, user_data: UserCreate, role: Optional[UserRole] = None) -> User:
        """Create a new user.

        Args:
            user_data: User creation data
            role: Optional role to assign (if None, auto-determined based on first user)

        Returns:
            User: Created user
        """
        # Check if user already exists
        existing_user = self.get_user_by_email(user_data.email)
        if existing_user:
            raise UserAlreadyExistsError("Email already registered")

        # Determine role: first user is always admin
        is_first = False
        if role is None:
            is_first = self.is_first_user()
            user_role = UserRole.ADMIN if is_first else UserRole.USER
        else:
            user_role = role

        # Create user
        hashed_password = get_password_hash(user_data.password)
        user = User(
            email=user_data.email,
            password=hashed_password,
            name=user_data.name,
            role=user_role
        )

        self.session.add(user)
        try:
            # Flush to assign identifiers and catch integrity issues early
            self.session.flush()
            # Create default user settings without committing
            self.create_user_settings(user.id, UserSettingsCreate(), commit=False)
            self.session.commit()
            self.session.refresh(user)

            if is_first:
                log_info(f"First user created as admin: {user.email}")
        except IntegrityError as exc:
            self.session.rollback()
            raise UserAlreadyExistsError("Email already registered") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc, user_email=user.email)
            raise

        return user

    def update_user(self, user_id: str, user_data: UserUpdate) -> User:
        """Update user information."""
        user = self.get_user_by_id(user_id)
        if not user:
            raise UserNotFoundError("User not found")

        # Handle password change if provided
        if user_data.current_password is not None and user_data.new_password is not None:
            # Check if user is OIDC user - OIDC users cannot change password
            if self.is_oidc_user(user_id):
                log_warning(
                    f"Password change rejected for OIDC user: {user.email}"
                )
                raise ValueError("Password cannot be changed for OIDC users. Please change your password through your OIDC provider.")

            # Verify current password
            if not verify_password(user_data.current_password, user.password):
                log_warning(
                    f"Password change failed for {user.email}: current password mismatch"
                )
                raise InvalidCredentialsError("Current password is incorrect")

            # Update password
            user.password = get_password_hash(user_data.new_password)

        # Update other fields
        if user_data.name is not None:
            user.name = user_data.name
        if user_data.profile_picture_url is not None:
            user.profile_picture_url = user_data.profile_picture_url

        try:
            self.session.add(user)
            self.session.commit()
            self.session.refresh(user)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc, user_email=user.email)
            raise

        return user

    def delete_user(self, user_id: str, bypass_admin_check: bool = False) -> bool:
        """Permanently delete a user and all related data.

        All related data (journals, entries, media, tags, mood logs, prompts,
        settings, and writing streaks) are automatically deleted via
        database-level CASCADE constraints and ORM relationship cascades.

        Args:
            user_id: User ID to delete
            bypass_admin_check: If True, skip admin protection check (for self-deletion)

        Returns:
            bool: True if deletion successful
        """
        user = self.get_user_by_id(user_id)
        if not user:
            raise UserNotFoundError("User not found")

        # Check if user can be deleted (admin protection)
        if not bypass_admin_check:
            can_delete, error_msg = self.can_delete_user(user_id)
            if not can_delete:
                raise ValueError(error_msg)

        user_email = user.email

        # Delete the user - cascade deletion handles all related data
        self.session.delete(user)

        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc, user_email=user_email)
            raise

        log_info(f"User and all related data deleted via cascade: {user_email}")
        return True

    def authenticate_user(self, email: str, password: str) -> User:
        """Authenticate user with email and password."""
        user = self.get_user_by_email(email)
        if not user:
            # Perform dummy verify to keep timing consistent
            verify_password(password, _DUMMY_PASSWORD_HASH)
            time.sleep(0.05)
            raise InvalidCredentialsError("Incorrect email or password")

        if not verify_password(password, user.password):
            time.sleep(0.05)
            raise InvalidCredentialsError("Incorrect email or password")

        if not user.is_active:
            raise UnauthorizedError("User account is inactive")

        return user

    def create_user_settings(
        self,
        user_id: uuid.UUID,
        settings_data: UserSettingsCreate,
        *,
        commit: bool = True
    ) -> UserSettings:
        """Create user settings."""
        settings = UserSettings(
            user_id=user_id,
            **_schema_dump(settings_data)
        )

        self.session.add(settings)
        if commit:
            try:
                self.session.commit()
                self.session.refresh(settings)
            except SQLAlchemyError as exc:
                self.session.rollback()
                log_error(exc)
                raise
        else:
            self.session.flush()

        return settings

    def get_user_settings(self, user_id: str) -> UserSettings:
        """Get user settings."""
        try:
            user_uuid = uuid.UUID(user_id)
            statement = select(UserSettings).where(UserSettings.user_id == user_uuid)
            settings = self.session.exec(statement).first()
            if not settings:
                raise UserSettingsNotFoundError("User settings not found")
            return settings
        except ValueError:
            raise UserNotFoundError("Invalid user ID format")

    def update_user_settings(self, user_id: str, settings_data: UserSettingsUpdate) -> UserSettings:
        """Update user settings."""
        settings = self.get_user_settings(user_id)

        # Update fields
        update_data = _schema_dump(settings_data, exclude_unset=True)
        for field, value in update_data.items():
            setattr(settings, field, value)

        try:
            self.session.add(settings)
            self.session.commit()
            self.session.refresh(settings)
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc)
            raise

        return settings

    def get_user_timezone(self, user_id: uuid.UUID) -> str:
        """
        Get user's timezone from settings.

        Args:
            user_id: User UUID

        Returns:
            str: IANA timezone string (defaults to "UTC" if not set)
        """
        try:
            statement = select(UserSettings).where(UserSettings.user_id == user_id)
            settings = self.session.exec(statement).first()
            if settings and settings.time_zone:
                return settings.time_zone
        except Exception:
            pass
        return "UTC"

    def get_or_create_user_from_oidc(
        self,
        *,
        issuer: str,
        subject: str,
        email: Optional[str],
        name: Optional[str],
        picture: Optional[str],
        auto_provision: bool
    ) -> User:
        """
        Get or create user from OIDC authentication.

        Finds existing external identity or creates a new user if auto-provisioning is enabled.

        Args:
            issuer: OIDC issuer URL
            subject: OIDC subject identifier (unique per issuer)
            email: User email from OIDC provider
            name: User display name from OIDC provider
            picture: User profile picture URL from OIDC provider
            auto_provision: Whether to automatically create new users

        Returns:
            User: The authenticated user

        Raises:
            UnauthorizedError: If user not found and auto-provisioning is disabled
        """
        # Find existing ExternalIdentity by (issuer, subject)
        statement = select(ExternalIdentity).where(
            ExternalIdentity.issuer == issuer,
            ExternalIdentity.subject == subject
        )
        external_identity = self.session.exec(statement).first()

        if external_identity:
            # Update last login time and profile information
            external_identity.last_login_at = datetime.now(timezone.utc)
            if email:
                external_identity.email = email
            if name:
                external_identity.name = name
            if picture:
                external_identity.picture = picture

            try:
                self.session.add(external_identity)
                self.session.commit()
                self.session.refresh(external_identity)
            except SQLAlchemyError as exc:
                self.session.rollback()
                log_error(exc, issuer=issuer, subject=subject)
                raise

            # Load and return the associated user
            user = self.get_user_by_id(str(external_identity.user_id))
            if not user:
                raise UserNotFoundError(f"User {external_identity.user_id} not found for external identity")

            if not user.is_active:
                log_warning(f"OIDC login rejected for inactive user: {user.email}")
                raise UnauthorizedError("User account is inactive")

            log_info(f"OIDC login for existing user: {user.email}")
            return user

        # External identity not found - check if auto-provisioning is enabled
        if not auto_provision:
            log_warning(f"OIDC auto-provisioning disabled, rejecting new user from {issuer}")
            raise UnauthorizedError(
                "Your account is not registered. Please contact the administrator or "
                "register with email/password first."
            )

        # Auto-provision: find or create user by email
        user = None
        if email:
            user = self.get_user_by_email(email)
            if user and not user.is_active:
                log_warning(f"OIDC login rejected for inactive user: {email}")
                raise UnauthorizedError("User account is inactive")

        if not user:
            # Create new user
            if not email:
                raise ValueError("Cannot auto-provision user without email")

            # Determine role: first user is always admin
            is_first = self.is_first_user()
            user_role = UserRole.ADMIN if is_first else UserRole.USER

            # Generate a random password (user won't use it - OIDC only)
            # TODO: Reconsider this approach - what is OIDC is down and user wants to reset password and login?
            random_password = secrets.token_urlsafe(32)

            user = User(
                email=email,
                password=get_password_hash(random_password),
                name=name or email.split("@")[0],  # Use email prefix as default name
                is_active=True,
                role=user_role
            )

            self.session.add(user)

            try:
                # Flush to assign user ID
                self.session.flush()

                # Create default user settings
                self.create_user_settings(user.id, UserSettingsCreate(), commit=False)

                # Commit user creation
                self.session.commit()
                self.session.refresh(user)

                if is_first:
                    log_info(f"First user auto-provisioned from OIDC as admin: {user.email}")
                else:
                    log_info(f"Auto-provisioned new user from OIDC: {user.email}")
            except IntegrityError as exc:
                self.session.rollback()
                # Race condition: user was created between check and insert
                user = self.get_user_by_email(email)
                if not user:
                    raise UserAlreadyExistsError("Failed to create user") from exc
                log_info(f"User {email} created by another request, using existing user")
            except SQLAlchemyError as exc:
                self.session.rollback()
                log_error(exc, email=email)
                raise

        # 4. Create ExternalIdentity linking OIDC account to user
        external_identity = ExternalIdentity(
            user_id=user.id,
            issuer=issuer,
            subject=subject,
            email=email,
            name=name,
            picture=picture,
            last_login_at=datetime.now(timezone.utc)
        )

        self.session.add(external_identity)

        try:
            self.session.commit()
            self.session.refresh(external_identity)
            log_info(f"Created external identity for {user.email} from {issuer}")
        except IntegrityError as exc:
            self.session.rollback()
            # External identity already exists (race)
            statement = select(ExternalIdentity).where(
                ExternalIdentity.issuer == issuer,
                ExternalIdentity.subject == subject
            )
            existing = self.session.exec(statement).first()
            if existing:
                log_info(f"External identity for {issuer}/{subject} created by another request")
                # Update last login
                existing.last_login_at = datetime.now(timezone.utc)
                self.session.add(existing)
                self.session.commit()
            else:
                log_error(exc, issuer=issuer, subject=subject)
                raise
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc, issuer=issuer, subject=subject)
            raise

        return user

    # Admin-specific methods
    def get_all_users(self, limit: int = 100, offset: int = 0) -> list[User]:
        """Get all users (admin only).

        Args:
            limit: Maximum number of users to return
            offset: Number of users to skip

        Returns:
            list[User]: List of users with external_identities eagerly loaded
        """
        statement = (
            select(User)
            .options(selectinload(User.external_identities))
            .limit(limit)
            .offset(offset)
            .order_by(User.created_at.desc())
        )
        return list(self.session.exec(statement).all())

    def create_user_as_admin(self, user_data: AdminUserCreate) -> User:
        """Create a new user as admin (can specify role).

        Args:
            user_data: Admin user creation data with optional role

        Returns:
            User: Created user
        """
        # Check if user already exists
        existing_user = self.get_user_by_email(user_data.email)
        if existing_user:
            raise UserAlreadyExistsError("Email already registered")

        # Create user with specified role
        hashed_password = get_password_hash(user_data.password)
        user = User(
            email=user_data.email,
            password=hashed_password,
            name=user_data.name,
            role=user_data.role
        )

        self.session.add(user)
        try:
            # Flush to assign identifiers and catch integrity issues early
            self.session.flush()
            # Create default user settings without committing
            self.create_user_settings(user.id, UserSettingsCreate(), commit=False)
            self.session.commit()
            self.session.refresh(user)

            log_info(f"Admin created user with role {user.role}: {user.email}")
        except IntegrityError as exc:
            self.session.rollback()
            raise UserAlreadyExistsError("Email already registered") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc, user_email=user.email)
            raise

        return user

    def update_user_as_admin(self, user_id: str, user_data: AdminUserUpdate) -> User:
        """Update user as admin (can change role, email, active status).

        Args:
            user_id: User ID to update
            user_data: Admin user update data

        Returns:
            User: Updated user
        """
        user = self.get_user_by_id(user_id)
        if not user:
            raise UserNotFoundError("User not found")

        # Check role change protection
        if user_data.role is not None and user_data.role != user.role:
            can_update, error_msg = self.can_update_user_role(user_id, user_data.role)
            if not can_update:
                raise ValueError(error_msg)

        # Update fields
        update_data = _schema_dump(user_data, exclude_unset=True)

        # Handle password separately
        if 'password' in update_data and update_data['password']:
            user.password = get_password_hash(update_data['password'])
            del update_data['password']

        # Update other fields
        for field, value in update_data.items():
            setattr(user, field, value)

        try:
            self.session.add(user)
            self.session.commit()
            self.session.refresh(user)

            log_info(f"Admin updated user: {user.email}")
        except IntegrityError as exc:
            self.session.rollback()
            if 'email' in str(exc).lower():
                raise UserAlreadyExistsError("Email already registered") from exc
            raise
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc, user_email=user.email)
            raise

        return user
