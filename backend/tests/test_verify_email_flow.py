"""Prueba de ida y vuelta del link de verificación de email.

Regresión (issue #132): el handler de ``/verify-email/request`` guardaba solo
el hash del token y ponía ESE hash en el link del email, pero
``/verify-email/confirm`` hashea lo que recibe y lo compara contra el hash
guardado → ``sha256(sha256(token))`` nunca coincide y el confirm respondía
siempre ``400 INVALID_TOKEN``.

El link de verificación era inservible. Y como el checkout exige email
verificado ("Email verification required to purchase plans"), el camino de
venta quedaba bloqueado: el usuario no podia confirmar su email y por lo tanto
no podia comprar un plan.

Los tests que ya existian no lo detectaban porque sembraban su propia fila de
token (con el plaintext a mano) en vez de pasar por el handler que genera el
link. Este test recorre el camino real: pedir el link → parsearlo del email →
confirmar con ese token.
"""

import re

from sqlmodel import select

from app.core.security import create_access_token
from app.db.models import EmailVerificationToken, User

TOKEN_IN_LINK = re.compile(r"token=([A-Za-z0-9_\-]+)")


async def _create_user(clean_db, email: str, user_id: int) -> User:
    async with clean_db.session_factory() as session:
        user = User(
            id=user_id,
            email=email,
            password_hash="hashed",
            role="job_seeker",
            full_name="Verify Flow",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def test_verification_link_from_the_email_confirms_the_account(
    async_client, clean_db, monkeypatch
) -> None:
    """El token del link debe servir tal cual para confirmar el email."""
    user = await _create_user(clean_db, "verify-flow@example.com", 91)
    token_header = {
        "Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'role': 'job_seeker'})}"
    }

    captured: dict[str, str] = {}

    async def _capture(to, subject, html_body=None, text_body=None, **kwargs):  # noqa: ANN001
        captured["html"] = html_body or ""
        captured["text"] = text_body or ""
        return True

    monkeypatch.setattr("app.api.v1.auth.email_service.send_email_async", _capture)

    # 1) Pedir el link.
    response = await async_client.post("/v1/auth/verify-email/request", headers=token_header)
    assert response.status_code == 202, response.text

    # 2) El link debe traer un token (crudo) y no el hash guardado.
    match = TOKEN_IN_LINK.search(captured["text"])
    assert match, f"el email no trae link con token: {captured['text']!r}"
    link_token = match.group(1)

    async with clean_db.session_factory() as session:
        result = await session.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
        )
        row = result.scalars().one()
        assert row.token_hash != link_token, (
            "el link debe llevar el token crudo: si lleva el hash, el confirm "
            "lo hashea de nuevo y siempre responde INVALID_TOKEN"
        )

    # 3) Confirmar con el token del link.
    confirm = await async_client.post(
        "/v1/auth/verify-email/confirm", json={"token": link_token}
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json() == {"detail": "Email verified"}

    # 4) El usuario queda verificado.
    async with clean_db.session_factory() as session:
        result = await session.execute(select(User).where(User.id == user.id))
        assert result.scalars().one().email_verified_at is not None


async def test_confirmation_with_the_stored_hash_is_rejected(
    async_client, clean_db, monkeypatch
) -> None:
    """Guard de contrato: el hash NO sirve para confirmar.

    Documenta por qué el link tiene que llevar el token crudo — si alguien
    'arregla' el link para mandar el hash, este test lo frena.
    """
    user = await _create_user(clean_db, "verify-hash@example.com", 92)
    token_header = {
        "Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'role': 'job_seeker'})}"
    }

    async def _capture(*args, **kwargs):  # noqa: ANN001
        return True

    monkeypatch.setattr("app.api.v1.auth.email_service.send_email_async", _capture)

    response = await async_client.post("/v1/auth/verify-email/request", headers=token_header)
    assert response.status_code == 202

    async with clean_db.session_factory() as session:
        result = await session.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
        )
        stored_hash = result.scalars().one().token_hash

    confirm = await async_client.post(
        "/v1/auth/verify-email/confirm", json={"token": stored_hash}
    )
    assert confirm.status_code == 400
    assert confirm.json()["detail"] == "INVALID_TOKEN"
