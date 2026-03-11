import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { API_BASE_URL } from '../config';

interface User { id: number; username: string; name: string; role: string; }

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<string | null>;
  register: (username: string, password: string, displayName?: string, role?: string) => Promise<string | null>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);

  // 페이지 새로고침 시 localStorage에서 복원
  useEffect(() => {
    const savedToken = localStorage.getItem('token');
    const savedUser = localStorage.getItem('user');
    if (savedToken && savedUser) {
      try {
        setToken(savedToken);
        setUser(JSON.parse(savedUser));
      } catch {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
      }
    }
  }, []);

  const login = async (username: string, password: string): Promise<string | null> => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: '로그인 실패' }));
        return err.detail || '로그인 실패';
      }
      const data = await res.json();
      const userObj: User = {
        id: data.user.id,
        username: data.user.username,
        name: data.user.display_name || data.user.username,
        role: data.user.role,
      };
      setToken(data.access_token);
      setUser(userObj);
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('user', JSON.stringify(userObj));
      return null; // 성공
    } catch {
      return '서버에 연결할 수 없습니다.';
    }
  };

  const register = async (
    username: string, password: string, displayName?: string, role?: string
  ): Promise<string | null> => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username,
          password,
          display_name: displayName || username,
          role: role || 'user',
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: '회원가입 실패' }));
        return err.detail || '회원가입 실패';
      }
      const data = await res.json();
      const userObj: User = {
        id: data.user.id,
        username: data.user.username,
        name: data.user.display_name || data.user.username,
        role: data.user.role,
      };
      setToken(data.access_token);
      setUser(userObj);
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('user', JSON.stringify(userObj));
      return null;
    } catch {
      return '서버에 연결할 수 없습니다.';
    }
  };

  const logout = () => {
    setUser(null);
    setToken(null);
    localStorage.removeItem('token');
    localStorage.removeItem('user');
  };

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated: !!user, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth error');
  return context;
};
