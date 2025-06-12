import React, { useState } from 'react';
import { signUp } from '../api/auth';

interface RegisterProps {
  onRegisterSuccess: () => void;
  onNavigateToLogin: () => void;
}

const Register: React.FC<RegisterProps> = ({ onRegisterSuccess, onNavigateToLogin }) => {
  const [email, setEmail] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [firstName, setFirstName] = useState<string>('');
  const [lastName, setLastName] = useState<string>('');
  const [role, setRole] = useState<'student' | 'teacher'>('student'); // Default role
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await signUp(email, password, firstName, lastName, role);
      onRegisterSuccess();
    } catch (err: any) {
      setError(err.message || 'An unknown error occurred during registration.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="d-flex justify-content-center align-items-center vh-100 bg-dark-blue">
      <div className="card rounded-4 gradient-blue p-4" style={{ maxWidth: '400px', width: '100%' }}>
        <div className="card-body">
          <h2 className="card-title text-center text-white mb-4">Register</h2>
          {error && <div className="alert alert-danger">{error}</div>}
          <form onSubmit={handleSubmit}>
            <div className="mb-3">
              <label htmlFor="firstNameInput" className="form-label text-white-80">First Name</label>
              <input
                type="text"
                className="form-control bg-dark text-white border-secondary"
                id="firstNameInput"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                required
              />
            </div>
            <div className="mb-3">
              <label htmlFor="lastNameInput" className="form-label text-white-80">Last Name</label>
              <input
                type="text"
                className="form-control bg-dark text-white border-secondary"
                id="lastNameInput"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                required
              />
            </div>
            <div className="mb-3">
              <label htmlFor="emailInput" className="form-label text-white-80">Email address</label>
              <input
                type="email"
                className="form-control bg-dark text-white border-secondary"
                id="emailInput"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="mb-3">
              <label htmlFor="passwordInput" className="form-label text-white-80">Password</label>
              <input
                type="password"
                className="form-control bg-dark text-white border-secondary"
                id="passwordInput"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <div className="mb-3">
              <label htmlFor="roleSelect" className="form-label text-white-80">Role</label>
              <select
                className="form-select bg-dark text-white border-secondary"
                id="roleSelect"
                value={role}
                onChange={(e) => setRole(e.target.value as 'student' | 'teacher')}
                required
              >
                <option value="student">Student</option>
                <option value="teacher">Teacher</option>
              </select>
            </div>
            <button type="submit" className="btn btn-light w-100" disabled={loading}>
              {loading ? 'Registering...' : 'Register'}
            </button>
          </form>
          <p className="text-center text-white-80 mt-3">
            Already have an account? <a href="#" onClick={onNavigateToLogin} className="text-yellow text-decoration-none">Login here</a>
          </p>
        </div>
      </div>
    </div>
  );
};

export default Register; 