"""Grant or revoke an already verified user's moderator role from the server shell."""
import argparse

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from .config import Settings
from .email_auth import normalize_pku_email
from .models import ActionLog, LoginSession, User


def set_admin_role(database_url: str, email: str, role: str) -> bool:
    normalized = normalize_pku_email(email)
    if not normalized or role not in {'admin', 'student'}:
        raise ValueError('需要已验证的北大邮箱，以及 admin 或 student 身份')
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine) as db:
            user = db.scalar(select(User).where(User.email == normalized))
            if not user:
                raise ValueError('该邮箱尚未完成注册，请先验证邮箱并登录一次')
            if user.role == role:
                return False
            user.role = role
            db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
            db.add(ActionLog(actor_id=user.id, action='role.set.local_cli', target_id=user.id,
                             detail=f'服务器本机管理员命令设置为 {role}'))
            db.commit()
            return True
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description='调整已注册用户的管理员权限（仅在服务器本机执行）')
    parser.add_argument('action', choices=['grant', 'revoke'])
    parser.add_argument('email', help='已经通过验证码注册的北大邮箱')
    args = parser.parse_args()
    role = 'admin' if args.action == 'grant' else 'student'
    try:
        changed = set_admin_role(Settings().database_url, args.email, role)
    except ValueError as exc:
        parser.error(str(exc))
    print('已更新权限，请用户重新登录。' if changed else '该用户已经拥有目标权限。')


if __name__ == '__main__':
    main()
