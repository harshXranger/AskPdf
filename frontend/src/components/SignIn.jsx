import React, { useState, useEffect } from "react";
import { useGoogleLogin } from "@react-oauth/google";


const SignIn = ({ isOpen, onClose, user, setUser }) => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [isNewUser, setIsNewUser] = useState(false);
  const [step, setStep] = useState("login");
  const [googleLoading, setGoogleLoading] = useState(false);

  // ---------- REAL GOOGLE SIGN‑IN (hook called unconditionally) ----------
  const googleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      setGoogleLoading(true);
      try {
        const userInfo = await fetch(
          "https://www.googleapis.com/oauth2/v3/userinfo",
          { headers: { Authorization: `Bearer ${tokenResponse.access_token}` } }
        ).then((res) => res.json());

        const userData = {
          email: userInfo.email,
          name: userInfo.name,
          avatar: userInfo.picture || userInfo.name?.charAt(0).toUpperCase(),
          provider: "google",
        };
        setUser(userData);
        localStorage.setItem("askpdf_user", JSON.stringify(userData));
        setStep("success");
        setTimeout(() => {
          setGoogleLoading(false);
          onClose();
        }, 1500);
      } catch (error) {
        console.error("Failed to fetch Google profile", error);
        setGoogleLoading(false);
      }
    },
    onError: (error) => {
      console.error("Google login error", error);
      setGoogleLoading(false);
    },
  });

  // Reset state every time the modal opens
  useEffect(() => {
    if (isOpen) {
      setEmail("");
      setPassword("");
      setName("");
      setIsNewUser(false);
      setStep("login");
      setGoogleLoading(false);
    }
  }, [isOpen]);

  // ---------- Early return AFTER all hooks ----------
  if (!isOpen) return null;

  // ---------- Demo email / password (placeholder) ----------
  const handleEmailLogin = (e) => {
    e.preventDefault();
    if (!email || !password) return;
    setIsNewUser(true);
    setStep("complete");
  };

  const handleCompleteProfile = (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    const userData = {
      email,
      name: name.trim(),
      avatar: name.trim().charAt(0).toUpperCase(),
      provider: "email",
    };
    setUser(userData);
    localStorage.setItem("askpdf_user", JSON.stringify(userData));
    setStep("success");
    setTimeout(() => onClose(), 1500);
  };

  // ---------- Account details (when already logged in) ----------
  if (user) {
    return (
      <div className="signin-overlay" onClick={onClose}>
        <div className="signin-modal" onClick={(e) => e.stopPropagation()}>
          <button className="signin-close" onClick={onClose}>✕</button>
          <div className="signin-header">
            <h2>Your Account</h2>
          </div>
          <div className="account-details">
            <div className="account-avatar">
              {user.avatar?.startsWith("http") ? (
                <img src={user.avatar} alt="" className="avatar-img" />
              ) : (
                user.avatar
              )}
            </div>
            <div className="account-info">
              <strong>{user.name}</strong>
              <span>{user.email}</span>
              <span className="provider-badge">
                Signed in with {user.provider === "google" ? "Google" : "Email"}
              </span>
            </div>
          </div>
          <button
            className="signin-btn"
            onClick={() => {
              setUser(null);
              localStorage.removeItem("askpdf_user");
              onClose();
            }}
          >
            Sign out
          </button>
        </div>
      </div>
    );
  }

  // ---------- Login / Complete profile / Success steps ----------
  return (
    <div className="signin-overlay" onClick={onClose}>
      <div className="signin-modal" onClick={(e) => e.stopPropagation()}>
        <button className="signin-close" onClick={onClose}>✕</button>

        {step === "login" && (
          <>
            <div className="signin-header">
              <h2>Welcome back</h2>
              <p>Sign in to your AskPDF account</p>
            </div>

            <form onSubmit={handleEmailLogin} className="signin-form">
              <div className="input-group">
                <label>Email</label>
                <input
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div className="input-group">
                <label>Password</label>
                <input
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              <button type="submit" className="signin-btn">
                Sign In
              </button>
            </form>

            <div className="signin-divider">
              <span>or continue with</span>
            </div>

            <button
              className="google-btn"
              onClick={() => {
                if (!googleLoading) googleLogin();
              }}
              disabled={googleLoading}
            >
              {googleLoading ? (
                <span className="btn-spinner" />
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
              )}
              {googleLoading ? "Signing in…" : "Google"}
            </button>
          </>
        )}

        {step === "complete" && (
          <>
            <div className="signin-header">
              <h2>Complete your profile</h2>
              <p>Just one more step</p>
            </div>
            <form onSubmit={handleCompleteProfile} className="signin-form">
              <div className="input-group">
                <label>Your name</label>
                <input
                  type="text"
                  placeholder="John Doe"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>
              <button type="submit" className="signin-btn">
                Save & continue
              </button>
            </form>
          </>
        )}

        {step === "success" && (
          <div className="signin-success">
            <div className="success-icon">✓</div>
            <h2>You're all set!</h2>
            <p>Redirecting…</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default SignIn;