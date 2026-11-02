
"use client";

import type { ReactNode } from 'react';
import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { loginUser as apiLoginUser, registerUser as apiRegisterUser, refreshToken as apiRefreshToken, fetchUserProfile as apiFetchUserProfile } from '@/lib/api';
import type { User, AuthContextType, Token, AuthStatusResponse, UserPublicProfile, AuthRateLimitResponse, UserTag } from '@/types/auth';
import { useToast } from '@/hooks/use-toast';
import { useTranslation } from '@/hooks/useTranslation';
import { useRouter, usePathname } from 'next/navigation';
import { Loader2 } from 'lucide-react';

const AUTH_TOKEN_KEY = 'examAuthToken_v3'; // Ensure new key if format changes
const USER_UID_KEY = 'examUserUid_v3';

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isAdmin, setIsAdmin] = useState(false); // Still useful for quick checks
  const [isLoading, setIsLoading] = useState(true);
  const { toast } = useToast();
  const { t } = useTranslation();
  const router = useRouter();
  const disableAuth = process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true';
  const isRefreshingRef = useRef(false);
  const refreshIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const checkAdminStatus = (profile: UserPublicProfile | null): boolean => {
    return !!(profile && Array.isArray(profile.tags) && profile.tags.includes('ADMIN'));
  };

  const processUserLogin = useCallback((userData: User | null) => {
    setUser(userData);
    setIsAdmin(checkAdminStatus(userData?.profile || null));
  }, [setUser, setIsAdmin]);

  const fetchAndSetUserProfile = useCallback(async (token: string, uidForContext: string): Promise<UserPublicProfile | null> => {
    try {
      const profile = await apiFetchUserProfile(token);
      const newUser: User = { uid: uidForContext, token, profile };
      processUserLogin(newUser);
      return profile;
    } catch (error) {
      console.error("AuthContext: Failed to fetch user profile:", error);
      const newUser: User = { uid: uidForContext, token, profile: null };
      processUserLogin(newUser);
      // If profile fetch fails specifically due to 401/403, treat as logout
      if (error instanceof Error && (error.message.includes('401') || error.message.includes('403'))) {
        logout(); // Call logout which clears storage and redirects
      }
      return null;
    }
  }, [processUserLogin]); // Added logout to dependencies

  const logout = useCallback(() => {
    setUser(null);
    setIsAdmin(false);
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(USER_UID_KEY);
    if (refreshIntervalRef.current) {
      clearInterval(refreshIntervalRef.current);
      refreshIntervalRef.current = null;
    }
    if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/auth')) {
      router.push('/auth/login');
    }
  }, [router]);


  const refreshTokenIfNeeded = useCallback(async (tokenToRefresh?: string | null): Promise<boolean> => {
    if (disableAuth) return true;
    if (isRefreshingRef.current) return true;

    const tokenForAttempt = tokenToRefresh || localStorage.getItem(AUTH_TOKEN_KEY);
    if (!tokenForAttempt) {
      return false;
    }

    isRefreshingRef.current = true;
    try {
      const response = await apiRefreshToken(tokenForAttempt);
      if ('access_token' in response) {
        const newAccessToken = response.access_token;
        const currentUid = response.uid || localStorage.getItem(USER_UID_KEY) || 'unknown_uid_after_refresh';
        localStorage.setItem(AUTH_TOKEN_KEY, newAccessToken);
        localStorage.setItem(USER_UID_KEY, currentUid);
        await fetchAndSetUserProfile(newAccessToken, currentUid);
        return true;
      } else { // AuthStatusResponse (e.g. { detail: "..." })
        console.warn("Token refresh failed:", (response as AuthStatusResponse).detail);
        return false;
      }
    } catch (error: any) {
      console.error("AuthContext: Token refresh API call failed:", error);
      return false;
    } finally {
      isRefreshingRef.current = false;
    }
  }, [disableAuth, fetchAndSetUserProfile]);


  useEffect(() => {
    let isMounted = true;
    const loadUser = async () => {
      if (disableAuth) {
        const mockProfile: UserPublicProfile = { uid: 'test_user_admin', nickname: 'Test Admin (Auth Disabled)', email: null, qq: null, tags: ['ADMIN', 'USER', 'MANAGER'] as UserTag[] };
        const mockUser: User = { uid: mockProfile.uid, token: 'test_token_disabled_auth', profile: mockProfile };
        if (isMounted) {
          processUserLogin(mockUser);
          setIsLoading(false);
        }
        return;
      }

      setIsLoading(true);
      const storedToken = localStorage.getItem(AUTH_TOKEN_KEY);
      const storedUid = localStorage.getItem(USER_UID_KEY);

      if (storedToken && storedUid) {
        const refreshSuccess = await refreshTokenIfNeeded(storedToken);
        if (!refreshSuccess && isMounted) {
          logout();
        }
      } else {
        if (isMounted) processUserLogin(null);
      }
      if (isMounted) setIsLoading(false);
    };

    loadUser();
    return () => { isMounted = false; };
  }, [disableAuth, refreshTokenIfNeeded, logout, processUserLogin]);


  useEffect(() => {
    if (disableAuth || !user?.token || isLoading) return;
    if (refreshIntervalRef.current) clearInterval(refreshIntervalRef.current);

    refreshIntervalRef.current = setInterval(async () => {
      if (user?.token && !isRefreshingRef.current) {
        const refreshSuccess = await refreshTokenIfNeeded(user.token);
        if (!refreshSuccess) {
          logout();
          toast({ title: t('auth.toast.sessionExpired.title'), description: t('auth.toast.sessionExpired.description'), variant: "destructive" });
        }
      }
    }, 23 * 60 * 1000); // Approx 23 minutes

    return () => {
      if (refreshIntervalRef.current) clearInterval(refreshIntervalRef.current);
    };
  }, [user, isLoading, refreshTokenIfNeeded, logout, disableAuth, t, toast]);

  // Login now expects uid and password, will be sent as form-urlencoded by the proxy
  const login = async (uid: string, password_plaintext: string): Promise<Token | AuthStatusResponse | AuthRateLimitResponse> => {
    if (disableAuth) {
      const isAdminLogin = uid.includes('admin');
      const mockProfile: UserPublicProfile = { uid, nickname: isAdminLogin ? 'Test Admin' : 'Test User', email: null, qq: null, tags: isAdminLogin ? ['ADMIN', 'USER', 'MANAGER'] as UserTag[] : ['USER'] as UserTag[] };
      const mockUser: User = { uid, token: 'test_token_disabled_auth', profile: mockProfile };
      processUserLogin(mockUser);
      setIsLoading(false);
      return { access_token: mockUser.token, token_type: "bearer", uid };
    }

    setIsLoading(true);
    try {
      const response = await apiLoginUser(uid, password_plaintext);
      if ('access_token' in response) {
        localStorage.setItem(AUTH_TOKEN_KEY, response.access_token);
        const uidForContext = response.uid || uid; // Use UID from token response if available
        localStorage.setItem(USER_UID_KEY, uidForContext);
        await fetchAndSetUserProfile(response.access_token, uidForContext);
      } else {
        processUserLogin(null);
      }
      return response;
    } catch (error) {
      processUserLogin(null);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  // Register now calls POST /auth/signin
  const register = async (uid: string, password_plaintext: string, nickname?: string, email?: string, qq?: string): Promise<Token | AuthStatusResponse | AuthRateLimitResponse> => {
    if (disableAuth) {
      setIsLoading(false);
      return { access_token: "mock_token_for_disabled_auth_register", token_type: "bearer", uid };
    }
    setIsLoading(true);
    try {
      // API now is POST /auth/signin via /api/auth/signin
      const response = await apiRegisterUser(uid, password_plaintext, nickname, email, qq);
      return response; // Backend returns Token on 201, or error model
    } catch (error) {
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  const updateLocalUserProfile = useCallback((profile: UserPublicProfile) => {
    setUser(prevUser => {
      if (prevUser) {
        const updatedUser = { ...prevUser, profile };
        processUserLogin(updatedUser);
        return updatedUser;
      }
      return null;
    });
  }, [processUserLogin]);


  return (
    <AuthContext.Provider value={{ user, isAdmin, isLoading, login, register, logout, refreshToken: refreshTokenIfNeeded, fetchUserProfile: () => {
      if (user?.token && user?.uid) {
        return fetchAndSetUserProfile(user.token, user.uid);
      }
      return Promise.resolve(null);
    }, updateLocalUserProfile }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const ProtectedRoute = ({ children }: { children: ReactNode }) => {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const disableAuth = process.env.NEXT_PUBLIC_DISABLE_AUTH === 'true';

  useEffect(() => {
    if (disableAuth || isLoading) return;

    if (!user && !pathname.startsWith('/auth')) {
      router.push('/auth/login');
    }
  }, [user, isLoading, router, disableAuth, pathname]);

  if (!disableAuth && isLoading) {
    return <div className="flex min-h-screen items-center justify-center"><Loader2 className="h-12 w-12 animate-spin text-primary" /></div>;
  }

  if (!disableAuth && !user && !pathname.startsWith('/auth')) {
    return <div className="flex min-h-screen items-center justify-center"><Loader2 className="h-12 w-12 animate-spin text-primary" /></div>;
  }

  return <>{children}</>;
};
