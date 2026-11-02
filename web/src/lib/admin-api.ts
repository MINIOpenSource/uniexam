import type {
  PaperAdminView,
  QuestionBankResponse,
  QuestionModel,
  PaperFullDetailModel,
  SettingsResponseModel,
  SettingsUpdatePayload,
  AdminUserUpdate,
  UserPublicProfile,
  LibraryIndexItem,
  PendingGradingPaperItem,
  SubjectiveQuestionForGrading,
  GradeSubmissionPayload
} from '@/types/admin';
import type { DifficultyLevel } from '@/types/auth';

const buildAdminApiUrl = (path: string, params?: Record<string, string | number | undefined | null>): string => {
  const url = new URL(`/api/admin${path}`, window.location.origin);
  if (params) {
    for (const key in params) {
      if (params[key] !== undefined && params[key] !== null) {
        url.searchParams.append(key, String(params[key]));
      }
    }
  }
  return url.toString();
};

const authHeaders = (token: string, extra?: Record<string, string>): Record<string, string> => ({
  Authorization: `Bearer ${token}`,
  ...extra,
});

export async function fetchAdminPapers(
  token: string,
  skip: number = 0,
  limit: number = 100,
  user_uid?: string,
  difficulty?: DifficultyLevel,
  status?: string,
  format?: 'csv' | 'xlsx'
): Promise<PaperAdminView[] | Blob> {
  const queryParams: Record<string, string | number | undefined> = { skip, limit, user_uid, difficulty, status, format };
  const url = buildAdminApiUrl('/papers_list', queryParams);

  const response = await fetch(url, {
    cache: 'no-store',
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: `Failed to fetch papers: ${response.status} ${response.statusText}` }));
    throw new Error(errorData.detail);
  }
  if (format) {
    return response.blob();
  }
  return response.json();
}

export async function fetchAdminPaperDetails(token: string, paperId: string): Promise<PaperFullDetailModel> {
  const url = buildAdminApiUrl(`/paper_detail/${paperId}`);

  const response = await fetch(url, {
    cache: 'no-store',
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: `Failed to fetch paper details for ${paperId}: ${response.status} ${response.statusText}` }));
    throw new Error(errorData.detail);
  }
  return response.json();
}

export async function deleteAdminPaper(token: string, paperId: string): Promise<void> {
  const url = buildAdminApiUrl(`/paper_delete/${paperId}`);

  const response = await fetch(url, {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  if (!response.ok && response.status !== 204) {
    const errorData = await response.json().catch(() => ({ detail: `Failed to delete paper ${paperId}` }));
    throw new Error(errorData.detail || `Failed to delete paper ${paperId}: ${response.status} ${response.statusText}`);
  }
}

export async function fetchAdminQuestionBankIndex(token: string): Promise<LibraryIndexItem[]> {
  const url = buildAdminApiUrl('/question_banks_index');
  const response = await fetch(url, {
    cache: 'no-store',
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: `Failed to fetch question bank index: ${response.status}` }));
    throw new Error(errorData.detail);
  }
  return response.json();
}

export async function fetchQuestionBankContent(token: string, difficultyId: DifficultyLevel): Promise<QuestionBankResponse> {
  const url = buildAdminApiUrl(`/question_bank_content/${difficultyId}`);

  const response = await fetch(url, {
    cache: 'no-store',
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: `Failed to fetch ${difficultyId} question bank content: ${response.status}` }));
    throw new Error(errorData.detail);
  }
  return response.json();
}

export async function addQuestionToBank(token: string, difficultyId: DifficultyLevel, payload: QuestionModel): Promise<QuestionModel> {
  const url = buildAdminApiUrl(`/question_bank_add/${difficultyId}`);

  const response = await fetch(url, {
    method: 'POST',
    headers: authHeaders(token, { 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  });
  if (!response.ok && response.status !== 201) {
    const errorData = await response.json().catch(() => ({ detail: `Failed to add question to ${difficultyId} bank` }));
    throw new Error(errorData.detail || `Failed to add question: ${response.status}`);
  }
  return response.json();
}

export async function deleteQuestionFromBank(token: string, difficultyId: DifficultyLevel, questionIndex: number): Promise<void> {
  const queryParams = { index: questionIndex };
  const url = buildAdminApiUrl(`/question_bank_delete/${difficultyId}`, queryParams);

  const response = await fetch(url, {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  if (!response.ok && response.status !== 204) {
    const errorData = await response.json().catch(() => ({ detail: `Failed to delete question ${questionIndex} from ${difficultyId} bank` }));
    throw new Error(errorData.detail || `Failed to delete question: ${response.status}`);
  }
}

export async function fetchAdminSettings(token: string): Promise<SettingsResponseModel> {
  const url = buildAdminApiUrl('/settings');
  const response = await fetch(url, {
    cache: 'no-store',
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: `Failed to fetch admin settings: ${response.status}` }));
    throw new Error(errorData.detail);
  }
  return response.json();
}

export async function updateAdminSettings(token: string, payload: SettingsUpdatePayload): Promise<SettingsResponseModel> {
  const url = buildAdminApiUrl('/settings');
  const response = await fetch(url, {
    method: 'POST',
    headers: authHeaders(token, { 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: `Failed to update admin settings` }));
    throw new Error(errorData.detail || `Failed to update settings: ${response.status}`);
  }
  return response.json();
}

export async function fetchAdminUsers(token: string, skip: number = 0, limit: number = 100, format?: 'csv' | 'xlsx'): Promise<UserPublicProfile[] | Blob> {
  const queryParams = { skip, limit, format };
  const url = buildAdminApiUrl('/users_list', queryParams);
  const response = await fetch(url, {
    cache: 'no-store',
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: `Failed to fetch users: ${response.status}` }));
    throw new Error(errorData.detail);
  }
  if (format) {
    return response.blob();
  }
  return response.json();
}

export async function fetchAdminUserDetail(token: string, userUid: string): Promise<UserPublicProfile> {
  const url = buildAdminApiUrl(`/users_detail/${userUid}`);
  const response = await fetch(url, {
    cache: 'no-store',
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: `Failed to fetch user details for ${userUid}: ${response.status}` }));
    throw new Error(errorData.detail);
  }
  return response.json();
}

export async function updateAdminUser(token: string, userUid: string, payload: AdminUserUpdate): Promise<UserPublicProfile> {
  const url = buildAdminApiUrl(`/users_update/${userUid}`);
  const response = await fetch(url, {
    method: 'PUT',
    headers: authHeaders(token, { 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: `Failed to update user ${userUid}` }));
    throw new Error(errorData.detail || `Failed to update user ${userUid}: ${response.status}`);
  }
  return response.json();
}

export async function fetchPendingGradingPapers(token: string, skip: number = 0, limit: number = 100): Promise<PendingGradingPaperItem[]> {
  const url = buildAdminApiUrl('/grading/pending_papers', { skip, limit });
  const response = await fetch(url, {
    cache: 'no-store',
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch pending grading papers' }));
    throw new Error(errorData.detail);
  }
  return response.json();
}

export async function fetchSubjectiveQuestionsForGrading(token: string, paperId: string): Promise<SubjectiveQuestionForGrading[]> {
  const url = buildAdminApiUrl(`/grading/papers/${paperId}/subjective_questions`);
  const response = await fetch(url, {
    cache: 'no-store',
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: `Failed to fetch subjective questions for paper ${paperId}` }));
    throw new Error(errorData.detail);
  }
  return response.json();
}

export async function submitSubjectiveGrade(token: string, paperId: string, questionInternalId: string, payload: GradeSubmissionPayload): Promise<void> {
  const url = buildAdminApiUrl(`/grading/papers/${paperId}/questions/${questionInternalId}/grade`);
  const response = await fetch(url, {
    method: 'POST',
    headers: authHeaders(token, { 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  });
  if (!response.ok && response.status !== 204) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to submit grade' }));
    throw new Error(errorData.detail);
  }
}

export async function fetchActiveTokens(token: string): Promise<any[]> {
  const url = buildAdminApiUrl('/tokens_list');
  const response = await fetch(url, {
    cache: 'no-store',
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: 'Failed to fetch active tokens' }));
    throw new Error(errorData.detail);
  }
  return response.json();
}

export async function revokeUserTokens(token: string, userUid: string): Promise<{message: string; invalidated_count: number}> {
  const url = buildAdminApiUrl(`/tokens_revoke_user/${userUid}`);
  const response = await fetch(url, {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ detail: `Failed to revoke tokens for user ${userUid}` }));
    throw new Error(errorData.detail);
  }
  return response.json();
}

export async function revokeSingleToken(adminToken: string, tokenToRevoke: string): Promise<void> {
  const url = buildAdminApiUrl(`/tokens_revoke_single/${tokenToRevoke}`);
  const response = await fetch(url, {
    method: 'DELETE',
    headers: authHeaders(adminToken),
  });
  if (!response.ok && response.status !== 204) {
    const errorData = await response.json().catch(() => ({ detail: `Failed to revoke token ${tokenToRevoke}` }));
    throw new Error(errorData.detail);
  }
}
