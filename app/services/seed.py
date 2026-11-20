import logging
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_api_key, hash_password
from app.db.models import Gateway, User

logger = logging.getLogger("smarttrap")


def sync_gateway_key(db: Session) -> None:
    current = hash_api_key(settings.gateway_api_key)
    gateways = db.scalars(select(Gateway)).all()
    changed = False
    for gateway in gateways:
        if gateway.api_key_hash != current:
            gateway.api_key_hash = current
            changed = True
    if changed:
        db.commit()
        logger.info("Chave do gateway alinhada com GATEWAY_API_KEY")


def seed(db: Session) -> None:
    sync_gateway_key(db)
    existing = db.scalar(select(func.count()).select_from(User))
    if existing:
        return

    emails = {settings.admin_email.lower(), settings.user_email.lower(), settings.demo_email.lower()}
    if len(emails) != 3:
        raise RuntimeError("ADMIN_EMAIL, USER_EMAIL e DEMO_EMAIL precisam ser diferentes")

    admin = User(
        name=settings.admin_name,
        email=settings.admin_email.lower(),
        password_hash=hash_password(settings.admin_password),
        role="superadmin",
        is_demo=False,
        is_active=True,
    )
    common = User(
        name=settings.user_name,
        email=settings.user_email.lower(),
        password_hash=hash_password(settings.user_password),
        role="common",
        is_demo=False,
        is_active=True,
    )
    demo = User(
        name=settings.demo_name,
        email=settings.demo_email.lower(),
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role="common",
        is_demo=True,
        is_active=True,
    )
    gateway = Gateway(name="Heltec", api_key_hash=hash_api_key(settings.gateway_api_key))
    db.add_all([admin, common, demo, gateway])
    db.commit()
    logger.info(
        "Seed de usuários criado: %s, %s, %s",
        admin.email,
        common.email,
        demo.email,
    )
    logger.info("Gateway API key (mostrada uma vez): %s", settings.gateway_api_key)
