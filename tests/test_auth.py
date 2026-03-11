"""
tests/test_auth.py
──────────────────
S1 + D1 + S2: 시크릿 정리, 파일 정리, JWT 인증 검증 테스트
"""
import pytest


# ============================================================
# S1: 시크릿 정리
# ============================================================

class TestSecretCleanup:
    """S1: DB 연결 환경변수화"""

    def test_database_url_from_env(self):
        """database.py가 환경변수 DATABASE_URL을 사용"""
        from core.database import SQLALCHEMY_DATABASE_URL
        # 환경변수가 설정되어 있든, fallback이든 URL 형식이어야 함
        assert "postgresql" in SQLALCHEMY_DATABASE_URL

    def test_env_example_exists(self):
        """S1-2: .env.example 파일 존재 확인"""
        from pathlib import Path
        env_example = Path(__file__).resolve().parent.parent / ".env.example"
        assert env_example.exists(), f".env.example not found at {env_example}"
        content = env_example.read_text(encoding="utf-8")
        assert "DATABASE_URL" in content
        assert "JWT_SECRET_KEY" in content
        assert "GOOGLE_API_KEY" in content

    def test_env_example_has_no_real_secrets(self):
        """.env.example에 실제 시크릿이 포함되지 않음"""
        from pathlib import Path
        content = (Path(__file__).resolve().parent.parent / ".env.example").read_text(encoding="utf-8")
        assert "AIzaSy" not in content  # real Google API key prefix
        assert "SETZ-" not in content   # real D-Wave token prefix
        assert "password1234" not in content


# ============================================================
# D1: 파일 정리
# ============================================================

class TestFileCleanup:
    """D1: 프로젝트 삭제 시 파일 정리 & 고아 파일 스크립트"""

    def test_project_router_has_upload_cleanup(self):
        """delete_project에 uploads/ 정리 로직 존재"""
        import inspect
        from core.project_router import delete_project
        source = inspect.getsource(delete_project)
        assert "shutil.rmtree" in source
        assert "UPLOAD_BASE" in source

    def test_cleanup_script_exists(self):
        """고아 파일 정리 스크립트 존재"""
        from pathlib import Path
        script = Path(__file__).resolve().parent.parent / "scripts" / "cleanup_orphan_uploads.py"
        assert script.exists()
        content = script.read_text(encoding="utf-8")
        assert "find_orphan_dirs" in content
        assert "--delete" in content


# ============================================================
# S2: JWT 인증
# ============================================================

class TestUserModel:
    """S2-1: UserDB 모델"""

    def test_user_model_exists(self):
        from core.models import UserDB
        assert hasattr(UserDB, "username")
        assert hasattr(UserDB, "hashed_password")
        assert hasattr(UserDB, "role")
        assert hasattr(UserDB, "is_active")

    def test_user_table_schema(self):
        from core.models import UserDB
        assert UserDB.__tablename__ == "users"
        assert UserDB.__table_args__["schema"] == "core"


class TestAuthModule:
    """S2-2: core/auth.py"""

    def test_hash_and_verify_password(self):
        from core.auth import hash_password, verify_password
        hashed = hash_password("test1234")
        assert hashed != "test1234"
        assert verify_password("test1234", hashed)
        assert not verify_password("wrong", hashed)

    def test_create_access_token(self):
        from core.auth import create_access_token
        token = create_access_token({"sub": "testuser", "role": "user"})
        assert isinstance(token, str)
        assert len(token) > 20

    def test_decode_access_token(self):
        from core.auth import create_access_token, SECRET_KEY, ALGORITHM
        from jose import jwt
        token = create_access_token({"sub": "admin", "role": "admin"})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "admin"
        assert payload["role"] == "admin"
        assert "exp" in payload

    def test_expired_token_raises(self):
        from core.auth import create_access_token, SECRET_KEY, ALGORITHM
        from jose import jwt, ExpiredSignatureError
        from datetime import timedelta
        token = create_access_token({"sub": "x"}, expires_delta=timedelta(seconds=-1))
        with pytest.raises(ExpiredSignatureError):
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

    def test_oauth2_scheme_defined(self):
        from core.auth import oauth2_scheme
        assert oauth2_scheme.scheme_name == "OAuth2PasswordBearer"

    def test_get_current_user_callable(self):
        from core.auth import get_current_user
        assert callable(get_current_user)

    def test_require_admin_callable(self):
        from core.auth import require_admin
        assert callable(require_admin)


class TestAuthRouter:
    """S2-3: auth_router.py"""

    def test_router_registered(self):
        from core.auth_router import router
        paths = [r.path for r in router.routes]
        # Routes include prefix: /api/auth/register etc.
        assert any("register" in p for p in paths)
        assert any("login" in p for p in paths)
        assert any("me" in p for p in paths)

    def test_register_schema(self):
        from core.auth_router import RegisterRequest
        req = RegisterRequest(username="test", password="pw1234")
        assert req.username == "test"
        assert req.role == "user"

    def test_login_schema(self):
        from core.auth_router import LoginRequest
        req = LoginRequest(username="admin", password="admin1234")
        assert req.username == "admin"

    def test_token_response_schema(self):
        from core.auth_router import TokenResponse, UserOut
        user = UserOut(id=1, username="test", display_name="Test", role="user")
        resp = TokenResponse(access_token="abc", user=user)
        assert resp.token_type == "bearer"


class TestProjectRouterAuth:
    """S2-4: project_router.py에 get_current_user 적용"""

    def test_create_project_requires_auth(self):
        import inspect
        from core.project_router import create_project
        sig = inspect.signature(create_project)
        params = list(sig.parameters.keys())
        assert "current_user" in params

    def test_get_projects_requires_auth(self):
        import inspect
        from core.project_router import get_projects
        sig = inspect.signature(get_projects)
        params = list(sig.parameters.keys())
        assert "current_user" in params

    def test_delete_project_requires_auth(self):
        import inspect
        from core.project_router import delete_project
        sig = inspect.signature(delete_project)
        params = list(sig.parameters.keys())
        assert "current_user" in params

    def test_no_query_param_user_role(self):
        """user/role Query param이 제거되었는지 확인"""
        import inspect
        from core.project_router import get_projects
        sig = inspect.signature(get_projects)
        assert "user" not in sig.parameters
        assert "role" not in sig.parameters


class TestSettingsRouterAuth:
    """settings_router.py에 JWT 적용"""

    def test_get_solver_settings_requires_auth(self):
        import inspect
        from core.settings_router import get_solver_settings
        sig = inspect.signature(get_solver_settings)
        assert "current_user" in sig.parameters

    def test_update_solver_settings_requires_admin(self):
        import inspect
        from core.settings_router import update_solver_settings
        sig = inspect.signature(update_solver_settings)
        assert "current_user" in sig.parameters


class TestMainAppAuth:
    """main.py에 auth_router 등록 및 기존 엔드포인트 인증"""

    def test_auth_router_registered(self):
        from main import app
        paths = [r.path for r in app.routes]
        assert "/api/auth/login" in paths
        assert "/api/auth/register" in paths

    def test_menus_requires_auth(self):
        import inspect
        from main import get_my_menus
        sig = inspect.signature(get_my_menus)
        assert "current_user" in sig.parameters

    def test_chat_history_requires_auth(self):
        import inspect
        from main import get_chat_history
        sig = inspect.signature(get_chat_history)
        assert "current_user" in sig.parameters


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
