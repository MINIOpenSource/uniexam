import type { ExamPaperResponse, PaperSubmissionPayload, UpdateProgressResponse, GradingResultResponse, Difficulty } from '@/types/exam';
import type { Token, AuthStatusResponse, UserCreatePayload, HistoryItem, HistoryPaperDetailResponse, UserPublicProfile, UserProfileUpdate, UserPasswordUpdate, AuthRateLimitResponse, UserDirectoryEntry } from '@/types/auth';

const authHeaders = (token: string, extra?: Record<string, string>): Record<string, string> => ({
  Authorization: `Bearer ${token}`,
  ...extra,
});

export async function registerUser(uid: string, password_plaintext: string, nickname?: string, email?: string, qq?: string): Promise<Token | AuthStatusResponse | AuthRateLimitResponse> {
  const payload: UserCreatePayload = { uid, password: password_plaintext, nickname, email, qq };
  const response = await fetch("/api/auth/signin", {
    method: "POST",
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok && response.status !== 201) {
    throw new Error(data.detail || `API Error: ${response.status} ${response.statusText}`);
  }
  return data;
}

export async function loginUser(uid: string, password_plaintext: string): Promise<Token | AuthStatusResponse | AuthRateLimitResponse> {
  const payload: UserCreatePayload = { uid, password: password_plaintext };
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || `API Error: ${response.status} ${response.statusText}`);
  }
  return data;
}

export async function refreshToken(oldToken: string): Promise<Token | AuthStatusResponse> {
  const response = await fetch(`/api/auth/login_refresh`, {
    method: 'GET',
    headers: authHeaders(oldToken),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || `API Error: ${response.status} ${response.statusText}`);
  }
  return data;
}

export async function fetchUserProfile(token: string): Promise<UserPublicProfile | null> {
  const response = await fetch(`/api/user/profile`, {
    method: 'GET',
    headers: authHeaders(token),
  });
  if (!response.ok) {
    if (response.status === 401 || response.status === 403 || response.status === 404) {
      const errorData = await response.json().catch(() => ({ detail: 'Unauthorized or user not found' }));
      console.warn(`Fetch user profile failed: ${errorData.detail}`);
      return null;
    }
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch profile' }));
    throw new Error(errorData.detail || `API Error: ${response.status}`);
  }
  return response.json();
}

export async function updateUserProfile(token: string, profileData: UserProfileUpdate): Promise<UserPublicProfile> {
  const response = await fetch(`/api/user/profile`, {
    method: "PUT",
    headers: authHeaders(token, { 'Content-Type': 'application/json' }),
    body: JSON.stringify(profileData),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || `API Error updating profile: ${response.status}`);
  }
  return data;
}

export async function updateUserPassword(token: string, passwordData: UserPasswordUpdate): Promise<void> {
  const response = await fetch(`/api/user/password`, {
    method: "PUT",
    headers: authHeaders(token, { 'Content-Type': 'application/json' }),
    body: JSON.stringify(passwordData),
  });
  if (!response.ok && response.status !== 204) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to update password' }));
    throw new Error(errorData.detail || `API Error updating password: ${response.status}`);
  }
}

export async function fetchExamPaper(token: string, difficulty?: Difficulty | null, num_questions?: number | null): Promise<ExamPaperResponse> {
  const params = new URLSearchParams();
  if (difficulty) params.append('difficulty', difficulty);
  if (num_questions !== null && num_questions !== undefined) params.append('num_questions', String(num_questions));

  const qs = params.toString();
  const url = qs ? `/api/exam/get_exam?${qs}` : `/api/exam/get_exam`;
  const response = await fetch(url, {
    method: "GET",
    headers: authHeaders(token),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || `API Error fetching exam paper: ${response.status}`);
  }
  return data;
}

export async function updateExamProgress(token: string, submission: PaperSubmissionPayload): Promise<UpdateProgressResponse> {
  const response = await fetch(`/api/exam/update`, {
    method: "POST",
    headers: authHeaders(token, { 'Content-Type': 'application/json' }),
    body: JSON.stringify(submission),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || `API Error updating progress: ${response.status}`);
  }
  return data;
}

export async function finishExamSubmission(token: string, submission: PaperSubmissionPayload): Promise<GradingResultResponse> {
  const response = await fetch(`/api/exam/finish`, {
    method: "POST",
    headers: authHeaders(token, { 'Content-Type': 'application/json' }),
    body: JSON.stringify(submission),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || `API Error finishing exam: ${response.status}`);
  }
  return data;
}

export async function fetchUserHistory(token: string, format?: 'csv' | 'xlsx'): Promise<HistoryItem[] | Blob> {
  const params = new URLSearchParams();
  if (format) params.append('format', format);

  const qs = params.toString();
  const url = qs ? `/api/history/user?${qs}` : `/api/history/user`;
  const response = await fetch(url, {
    method: 'GET',
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch history' }));
    throw new Error(errorData.detail || `API Error fetching history: ${response.status}`);
  }
  if (format) {
    return response.blob();
  }
  return response.json();
}

export async function fetchHistoryPaperDetails(token: string, paperId: string): Promise<HistoryPaperDetailResponse> {
  const params = new URLSearchParams();
  params.append('paper_id', paperId);

  const response = await fetch(`/api/history/paper?${params.toString()}`, {
    method: 'GET',
    headers: authHeaders(token),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || `API Error fetching history paper details: ${response.status}`);
  }
  return data;
}

export async function fetchDifficulties(): Promise<any[]> {
  const response = await fetch(`/api/public/difficulties`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch difficulties' }));
    throw new Error(errorData.detail || `API Error: ${response.status}`);
  }
  return response.json();
}

export async function fetchUsersDirectory(): Promise<UserDirectoryEntry[]> {
  const response = await fetch(`/api/public/users_directory`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch user directory' }));
    throw new Error(errorData.detail || `API Error: ${response.status}`);
  }
  return response.json();
}
