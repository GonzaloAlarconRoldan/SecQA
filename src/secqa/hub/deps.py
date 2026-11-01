"""Shared FastAPI dependencies: DB session, auth, actor identity, lookups."""
from __future__ import annotations

import secrets
from collections.abc import Iterator
from typing import Annotated, TypeVar

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import Base, Project

M = TypeVar("M", bound=Base)


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    yield from request.app.state.db.session()


def require_token(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.api_token:
        return
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token, settings.api_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API token",
                            headers={"WWW-Authenticate": "Bearer"})


def get_actor(x_secqa_actor: Annotated[str | None, Header()] = None) -> str:
    actor = (x_secqa_actor or "human:anonymous").strip()[:100]
    return actor or "human:anonymous"


DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[str, Depends(get_actor)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]


def project_by_key(db: Session, key: str) -> Project:
    project = db.scalars(select(Project).where(Project.key == key.upper())).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"project '{key}' not found")
    return project


def get_or_404(db: Session, model: type[M], obj_id: int) -> M:
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} {obj_id} not found")
    return obj
