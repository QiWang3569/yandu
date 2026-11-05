from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.admin_cli import set_admin_role
from app.models import Base, LoginSession, User, now


def test_role_change_revokes_existing_sessions(tmp_path):
    url = f'sqlite:///{tmp_path / "admin.db"}'
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id='verified', nickname='已验证用户', campus='燕园校本部', email='user@stu.pku.edu.cn'))
        db.add(LoginSession(token_hash='token', user_id='verified', expires_at=now() + timedelta(days=1)))
        db.commit()
    assert set_admin_role(url, 'user@stu.pku.edu.cn', 'admin')
    with Session(engine) as db:
        assert db.get(User, 'verified').role == 'admin'
        assert db.get(LoginSession, 'token') is None
    engine.dispose()
