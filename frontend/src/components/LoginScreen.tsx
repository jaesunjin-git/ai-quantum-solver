import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Lock, Loader2, AlertCircle } from 'lucide-react';

const LoginScreen: React.FC = () => {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError('아이디와 비밀번호를 입력하세요.');
      return;
    }
    setLoading(true);
    setError(null);
    const err = await login(username.trim(), password);
    if (err) {
      setError(err);
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen items-center justify-center bg-slate-950">
      <div className="w-full max-w-md p-8 bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl">
        <div className="text-center mb-8">
          <Lock className="w-12 h-12 text-indigo-500 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-white">Quantum Solver</h1>
          <p className="text-slate-400">Enterprise Edition</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">ID</label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="admin"
              autoComplete="username"
              className="w-full p-3 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition"
            />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="password"
              autoComplete="current-password"
              className="w-full p-3 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition"
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 text-red-400 text-sm bg-red-900/20 p-3 rounded-lg">
              <AlertCircle size={16} />
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full p-4 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-bold flex justify-center items-center gap-2 transition disabled:opacity-50"
          >
            {loading ? <Loader2 className="animate-spin" size={18} /> : <Lock size={18} />}
            Login
          </button>
        </form>

        <p className="text-center text-slate-500 text-xs mt-6">
          Default: admin / admin1234 or user / user1234
        </p>
      </div>
    </div>
  );
};
export default LoginScreen;
