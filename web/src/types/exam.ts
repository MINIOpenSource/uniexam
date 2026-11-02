import type { DifficultyLevel, QuestionTypeEnum, PaperPassStatusEnum } from './auth';

export type Difficulty = DifficultyLevel;

export interface QuestionChoice {
  [id: string]: string; // UUID option ID -> choice text mapping
}

export interface ExamQuestion {
  body: string;
  choices: QuestionChoice; // Options mapped to per-issuance UUIDs and shuffled order
  question_type?: QuestionTypeEnum | string;
  obfuscated_font?: string; // Per-question base64 TTF font data URI
}

export type Question = ExamQuestion;

export interface ExamPaperResponse {
  paper_id: string;
  difficulty: DifficultyLevel;
  paper: ExamQuestion[];
  paper_hash?: string;
}

export type Paper = ExamPaperResponse;

export interface PaperSubmissionPayload {
  paper_id: string;
  paper?: ExamQuestion[];
  paper_hash?: string;
  result: (string | null)[];
  current_question_index?: number;
  device_id?: string;
}

export type Submission = PaperSubmissionPayload;

export interface UpdateProgressResponse {
  status_code: "PROGRESS_SAVED" | string;
  message: string;
  paper_id?: string | null;
  last_update_time_utc?: string | null;
}

export type UpdateApiResponse = UpdateProgressResponse;

export interface GradingResultResponse {
  status_code: PaperPassStatusEnum | string;
  message?: string | null;
  passcode?: string | null;
  score?: number | null;
  score_percentage?: number | null;
  previous_result?: string | null;
  pending_manual_grading_count?: number | null;
}

export type FinishApiResponse = GradingResultResponse;

export interface ResultPageDisplayData {
  status_code?: PaperPassStatusEnum | string | number;
  message?: string | null;
  passcode?: string | null;
  score?: number | null;
  score_percentage?: number | null;
  paperId?: string;
  durationMs?: number;
  pending_manual_grading_count?: number | null;
}

export type ExamState =
  | 'authenticating'
  | 'login_required'
  | 'selecting_difficulty'
  | 'confirming_url_action'
  | 'loading'
  | 'welcome'
  | 'taking'
  | 'confirming_submission'
  | 'submitting'
  | 'success'
  | 'failed'
  | 'pending_review'
  | 'rate_limited'
  | 'error'
  | 'admin_panel';

export type AutoSaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export type WsConnectionStatus = 'connected' | 'connecting' | 'disconnected';

export interface ConnectedDevice {
  user_id?: string;
  uid?: string;
  role?: string;
  device_id: string;
  device_name: string;
  ip_address: string;
  connected_at: string;
  active_paper_id?: string | null;
  paper_difficulty?: string | null;
  current_question_index: number;
  answered_count?: number;
  total_questions?: number;
  page_mode?: string;
  exam_state?: string;
  window_focused?: boolean;
  visibility_state?: string;
  pointer_in_viewport?: boolean;
  mouse_x?: number | null;
  mouse_y?: number | null;
  viewport_w?: number | null;
  viewport_h?: number | null;
  hovered_zone?: string;
  focus_loss_count?: number;
  leave_viewport_count?: number;
  dom_purged?: boolean;
  shield_master_on?: boolean;
  security_alert_count?: number;
  last_security_alert?: string | null;
  last_mouse_active_at?: string | null;
  last_active_at: string;
}

export interface AdminLiveEvent {
  id: string;
  timestamp: string;
  category: 'connection' | 'focus' | 'pointer' | 'security' | 'exam' | string;
  severity: 'info' | 'warning' | 'danger' | 'success' | string;
  uid: string;
  device_id: string;
  device_name: string;
  ip_address: string;
  message: string;
  paper_id?: string | null;
  question_index?: number | null;
}
