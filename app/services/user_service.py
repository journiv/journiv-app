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
from sqlalchemy import func

from app.core.config import settings
from app.core.exceptions import (
    UserNotFoundError,
    UserAlreadyExistsError,
    InvalidCredentialsError,
    UnauthorizedError,
    UserSettingsNotFoundError,
)
from app.core.logging_config import log_error, log_warning, log_info
from app.core.security import get_password_hash, verify_password
from app.models.user import User, UserSettings
from app.models.external_identity import ExternalIdentity
from app.models.enums import UserRole
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserSettingsCreate,
    UserSettingsUpdate,
    AdminUserCreate,
    AdminUserUpdate,
)

_DUMMY_PASSWORD_HASH = get_password_hash("journiv-dummy-password")


def _schema_dump(schema_obj, *, exclude_unset: bool = False):
    if hasattr(schema_obj, "model_dump"):
        return schema_obj.model_dump(exclude_unset=exclude_unset)
    return schema_obj.dict(exclude_unset=exclude_unset)


class UserService:
    def __init__(self, session: Session):
        self.session = session

    def is_first_user(self) -> bool:
        try:
            if "sqlite" in str(self.session.bind.url).lower():
                count = self.session.exec(select(func.count(User.id))).scalar() or 0
                return count == 0
            statement = select(User.id).limit(1).with_for_update()
            result = self.session.exec(statement).first()
            return result is None
        except Exception as exc:
            log_error(exc, context="is_first_user check")
            return False

    def count_admin_users(self) -> int:
        return (
            self.session.exec(
                select(func.count(User.id)).where(User.role == UserRole.ADMIN)
            ).scalar()
            or 0
        )

    def can_delete_user(self, user_id: str) -> tuple[bool, Optional[str]]:
        user = self.get_user_by_id(user_id)
        if not user:
            return False, "User not found"

        if user.role == UserRole.ADMIN:
            if self.count_admin_users() <= 1:
                return (
                    False,
                    "Cannot delete the last admin user. At least one admin must exist.",
                )
        return True, None

    def can_update_user_role(
        self, user_id: str, new_role: UserRole
    ) -> tuple[bool, Optional[str]]:
        user = self.get_user_by_id(user_id)
        if not user:
            return False, "User not found"

        if user.role == UserRole.ADMIN and new_role != UserRole.ADMIN:
            if self.count_admin_users() <= 1:
                return (
                    False,
                    "Cannot demote the last admin user. At least one admin must exist.",
                )
        return True, None

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        try:
            user_uuid = uuid.UUID(user_id)
            return (
                self.session.exec(select(User).where(User.id == user_uuid)).first()
            )
        except ValueError:
            return None

    def get_user_by_email(self, email: str) -> Optional[User]:
        statement = select(User).where(func.lower(User.email) == email.lower())
        return self.session.exec(statement).first()

    def is_oidc_user(self, user_id: str) -> bool:
        try:
            user_uuid = uuid.UUID(user_id)
            stmt = select(ExternalIdentity).where(
                ExternalIdentity.user_id == user_uuid
            )
            return self.session.exec(stmt).first() is not None
        except ValueError:
            return False

    def is_signup_disabled(self) -> bool:
        return settings.disable_signup

    def create_user(self, user_data: UserCreate, role: Optional[UserRole] = None) -> User:
        user_data.email = user_data.email.lower()
        if self.get_user_by_email(user_data.email):
            raise UserAlreadyExistsError("Email already registered")

        is_first = False
        if role is None:
            is_first = self.is_first_user()
            user_role = UserRole.ADMIN if is_first else UserRole.USER
        else:
            user_role = role

        user = User(
            email=user_data.email,
            password=get_password_hash(user_data.password),
            name=user_data.name,
            role=user_role,
        )

        self.session.add(user)
        try:
            self.session.flush()
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
        user = self.get_user_by_id(user_id)
        if not user:
            raise UserNotFoundError("User not found")

        if (
            user_data.current_password is not None
            and user_data.new_password is not None
        ):
            if self.is_oidc_user(user_id):
                raise ValueError(
                    "Password cannot be changed for OIDC users. "
                    "Please change your password through your OIDC provider."
                )
            if not verify_password(user_data.current_password, user.password):
                raise InvalidCredentialsError("Current password is incorrect")
            user.password = get_password_hash(user_data.new_password)

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
        user = self.get_user_by_id(user_id)
        if not user:
            raise UserNotFoundError("User not found")

        if not bypass_admin_check:
            ok, msg = self.can_delete_user(user_id)
            if not ok:
                raise ValueError(msg)

        email = user.email
        self.session.delete(user)

        try:
            self.session.commit()
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc, user_email=email)
            raise

        log_info(f"User and related data deleted via cascade: {email}")
        return True

    def authenticate_user(self, email: str, password: str) -> User:
        user = self.get_user_by_email(email)
        if not user:
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
        commit: bool = True,
    ) -> UserSettings:
        settings = UserSettings(user_id=user_id, **_schema_dump(settings_data))
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
        try:
            user_uuid = uuid.UUID(user_id)
            stmt = select(UserSettings).where(UserSettings.user_id == user_uuid)
            settings = self.session.exec(stmt).first()
            if not settings:
                raise UserSettingsNotFoundError("User settings not found")
            return settings
        except ValueError:
            raise UserNotFoundError("Invalid user ID format")

    def update_user_settings(
        self, user_id: str, settings_data: UserSettingsUpdate
    ) -> UserSettings:
        settings = self.get_user_settings(user_id)
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
        try:
            stmt = select(UserSettings).where(UserSettings.user_id == user_id)
            settings = self.session.exec(stmt).first()
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
        email_verified: bool,
        auto_provision: bool,
    ) -> User:
        if not email_verified:
            raise UnauthorizedError("Email not verified by identity provider")

        stmt = select(ExternalIdentity).where(
            ExternalIdentity.issuer == issuer,
            ExternalIdentity.subject == subject,
        )
        external_identity = self.session.exec(stmt).first()

        if external_identity:
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

            user = self.get_user_by_id(str(external_identity.user_id))
            if not user:
                raise UserNotFoundError(
                    f"User {external_identity.user_id} not found"
                )
            if not user.is_active:
                raise UnauthorizedError("User account is inactive")

            log_info(f"OIDC login: {user.email}")
            return user

        if not auto_provision:
            raise UnauthorizedError(
                "Your account is not registered. Please contact the administrator."
            )

        user = None
        if email:
            user = self.get_user_by_email(email)
            if user and not user.is_active:
                raise UnauthorizedError("User account is inactive")

        if not user:
            if not email:
                raise ValueError("Cannot auto-provision user without email")

            is_first = self.is_first_user()
            role = UserRole.ADMIN if is_first else UserRole.USER

            user = User(
                email=email,
                password=get_password_hash(secrets.token_urlsafe(32)),
                name=name or email.split("@")[0],
                is_active=True,
                role=role,
            )

            self.session.add(user)
            try:
                self.session.flush()
                self.create_user_settings(user.id, UserSettingsCreate(), commit=False)
                self.session.commit()
                self.session.refresh(user)
            except IntegrityError:
                self.session.rollback()
                user = self.get_user_by_email(email)
                if not user:
                    raise
            except SQLAlchemyError as exc:
                self.session.rollback()
                log_error(exc, email=email)
                raise

        external_identity = ExternalIdentity(
            user_id=user.id,
            issuer=issuer,
            subject=subject,
            email=email,
            name=name,
            picture=picture,
            last_login_at=datetime.now(timezone.utc),
        )

        self.session.add(external_identity)
        try:
            self.session.commit()
            self.session.refresh(external_identity)
        except IntegrityError:
            self.session.rollback()
            stmt = select(ExternalIdentity).where(
                ExternalIdentity.issuer == issuer,
                ExternalIdentity.subject == subject,
            )
            existing = self.session.exec(stmt).first()
            if existing:
                existing.last_login_at = datetime.now(timezone.utc)
                self.session.add(existing)
                self.session.commit()
            else:
                raise
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc, issuer=issuer, subject=subject)
            raise

        return user

    def get_all_users(self, limit: int = 100, offset: int = 0) -> list[User]:
        stmt = (
            select(User)
            .options(selectinload(User.external_identities))
            .limit(limit)
            .offset(offset)
            .order_by(User.created_at.desc())
        )
        return list(self.session.exec(stmt).all())

    def create_user_as_admin(self, user_data: AdminUserCreate) -> User:
        user_data.email = user_data.email.lower()
        if self.get_user_by_email(user_data.email):
            raise UserAlreadyExistsError("Email already registered")

        user = User(
            email=user_data.email,
            password=get_password_hash(user_data.password),
            name=user_data.name,
            role=user_data.role,
        )

        self.session.add(user)
        try:
            self.session.flush()
            self.create_user_settings(user.id, UserSettingsCreate(), commit=False)
            self.session.commit()
            self.session.refresh(user)
        except IntegrityError as exc:
            self.session.rollback()
            raise UserAlreadyExistsError("Email already registered") from exc
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc, user_email=user.email)
            raise

        return user

    def update_user_as_admin(
        self, user_id: str, user_data: AdminUserUpdate
    ) -> User:
        user = self.get_user_by_id(user_id)
        if not user:
            raise UserNotFoundError("User not found")

        if (
            user_data.role is not None
            and user_data.role != user.role
        ):
            ok, msg = self.can_update_user_role(user_id, user_data.role)
            if not ok:
                raise ValueError(msg)

        update_data = _schema_dump(user_data, exclude_unset=True)

        if "password" in update_data and update_data["password"]:
            user.password = get_password_hash(update_data["password"])
            del update_data["password"]

        if email := update_data.get("email"):
            update_data["email"] = email.lower()

        for field, value in update_data.items():
            setattr(user, field, value)

        try:
            self.session.add(user)
            self.session.commit()
            self.session.refresh(user)
        except IntegrityError as exc:
            self.session.rollback()
            if "email" in str(exc).lower():
                raise UserAlreadyExistsError("Email already registered") from exc
            raise
        except SQLAlchemyError as exc:
            self.session.rollback()
            log_error(exc, user_email=user.email)
            raise

        return user
