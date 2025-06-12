import React, { useState, useEffect } from 'react';
import StudentDashboard from './components/StudentDashboard';
import Login from './components/Login';
import Register from './components/Register';
import { getCurrentUser, signOut, listenToAuthChanges } from './api/auth';
import './index.css';

function App() {
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const authListener = listenToAuthChanges((event, session) => {
      if (session) {
        setCurrentUser(session.user);
      } else {
        setCurrentUser(null);
      }
      setLoading(false);
    });

    // Initial check for current user
    getCurrentUser().then(user => {
      setCurrentUser(user);
      setLoading(false);
    }).catch(error => {
      console.error("Error fetching initial user:", error);
      setLoading(false);
    });

    return () => {
      authListener?.unsubscribe();
    };
  }, []);

  const handleLoginSuccess = () => {
    // No need to explicitly change page here, useEffect will handle it via auth changes
  };

  const handleRegisterSuccess = () => {
    // No need to explicitly change page here, useEffect will handle it via auth changes
  };

  const handleNavigateToLogin = () => {
    // This won't be directly used as App.tsx now controls routing based on auth state
  };

  const handleLogout = async () => {
    try {
      await signOut();
      // Auth state change will be handled by the listener in useEffect
    } catch (error) {
      console.error("Error during logout:", error);
    }
  };

  const renderContent = () => {
    if (loading) {
      return <div className="text-white text-center py-5">Loading application...</div>;
    }

    if (currentUser) {
      return (
        <>
          <nav className="bg-dark-blue p-4 flex justify-between items-center">
            <div className="container mx-auto flex justify-between items-center">
              <span className="text-white text-2xl font-bold">AI Classroom Companion</span>
              <div className="flex items-center">
                <span className="text-white-75 mr-4">Welcome, {currentUser.user_metadata?.first_name || currentUser.email}!</span>
                <button className="bg-transparent border border-white text-white px-4 py-2 rounded-md hover:bg-white hover:text-dark-blue transition-colors duration-200" onClick={handleLogout}>
                  Logout
                </button>
              </div>
            </div>
          </nav>
          <StudentDashboard />
        </>
      );
    }

    // If not logged in, show login or register based on simple path/state
    // For simplicity, let's assume a route for /register otherwise login
    const path = window.location.pathname;
    if (path === '/register') {
      return <Register onRegisterSuccess={handleRegisterSuccess} onNavigateToLogin={handleNavigateToLogin} />;
    } else {
      return <Login onLoginSuccess={handleLoginSuccess} />;
    }
  };

  return <div className="App bg-blue-500">{renderContent()}</div>;
}

export default App;
