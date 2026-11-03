export type DifficultyLevel = "easy" | "hybrid" | "hard";

export type UserTag =
  | "USER"
  | "ADMIN"
  | "MANAGER"
  | "GRADER"
  | "EXAMINER"
  | "LIMITED"
  | "BANNED";

export interface UserCreatePayload {
  uid: string;
  password?: string;
  nickname?: string | null;
  email?: string | null;
  qq?: string | null;
}

export interface Token {
  access_token: string;
  token_type: "bearer";
  uid?: string;
}

export interface AuthStatusResponse {
  detail?: string;
  status_code?: string | number;
  message?: string;
}

export interface AuthRateLimitResponse {
  detail?: string;
  status_code?: string | number;
  message?: string;
}

export type AuthResponse = Token | AuthStatusResponse | AuthRateLimitResponse;

export interface UserPublicProfile {
  uid: string;
  nickname?: string | null;
  email?: string | null;
  qq?: string | null;
  tags: UserTag[];
}

export interface UserProfileUpdate {
  nickname?: string | null;
  email?: string | null;
  qq?: string | null;
}

export interface UserPasswordUpdate {
  current_password: string;
  new_password: string;
}

export interface AdminUserUpdate {
  nickname?: string | null;
  email?: string | null;
  qq?: string | null;
  tags?: UserTag[] | null;
  new_password?: string | null;
}

export interface UserDirectoryEntry {
  uid: string;
  nickname?: string | null;
  tags: UserTag[];
}

export interface User {
  uid: string;
  token: string;
  profile?: UserPublicProfile | null;
}

export interface AuthContextType {
  user: User | null;
  isAdmin: boolean;
  isLoading: boolean;
  login: (uid: string, password_plaintext: string) => Promise<Token | AuthStatusResponse | AuthRateLimitResponse>;
  register: (uid: string, password_plaintext: string, nickname?: string, email?: string, qq?: string) => Promise<Token | AuthStatusResponse | AuthRateLimitResponse>;
  logout: () => void;
  refreshToken: (currentToken?: string | null) => Promise<boolean>;
  fetchUserProfile: () => Promise<UserPublicProfile | null>;
  updateLocalUserProfile: (profile: UserPublicProfile) => void;
}

export interface HistoryItem {
  paper_id: string;
  difficulty: DifficultyLevel;
  score?: number | null;
  score_percentage?: number | null;
  pass_status?: PaperPassStatusEnum | string | null;
  submission_time_utc?: string | null;
}

export type QuestionTypeEnum =
  | "single_choice"
  | "multiple_choice"
  | "fill_in_blank"
  | "essay_question";

export interface HistoryPaperQuestionClientView {
  body: string;
  choices?: { [key: string]: string } | null;
  submitted_answer?: string | string[] | null;
}

export type PaperPassStatusEnum = "PASSED" | "FAILED" | "PENDING_REVIEW" | string;

export interface HistoryPaperDetailResponse {
  paper_id: string;
  difficulty: DifficultyLevel;
  user_uid: string;
  paper?: {
    body: string;
    choices: { [key: string]: string };
  }[];
  paper_hash?: string;
  paper_questions: HistoryPaperQuestionClientView[];
  score?: number | null;
  score_percentage?: number | null;
  submitted_answers_card?: (string | null)[] | null;
  pass_status?: PaperPassStatusEnum | string | null;
  passcode?: string | null;
  submission_time_utc?: string | null;
}
