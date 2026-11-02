import type {
  DifficultyLevel,
  QuestionTypeEnum,
  PaperPassStatusEnum,
  UserPublicProfile,
  UserTag,
  AdminUserUpdate,
} from './auth';

export type PaperDifficulty = DifficultyLevel;
export type { UserPublicProfile, UserTag, AdminUserUpdate };

export interface PaperAdminView {
  paper_id: string;
  user_uid: string;
  difficulty: DifficultyLevel;
  creation_time_utc: string;
  creation_ip?: string | null;
  last_update_time_utc?: string | null;
  last_update_ip?: string | null;
  submission_time_utc?: string | null;
  submission_ip?: string | null;
  finished_count: number;
  total_count: number;
  count?: number;
  correct_count?: number;
  score?: number | null;
  score_percentage?: number | null;
  pass_status?: PaperPassStatusEnum | string | null;
  passcode?: string | null;
  subjective_questions_count?: number | null;
  graded_subjective_questions_count?: number | null;
  pending_manual_grading_count?: number | null;
}

export type AdminPaper = PaperAdminView;

export interface PaperAdminQuestionDetailView {
  id?: string | number;
  body: string;
  question_type: QuestionTypeEnum | string;
  choices?: { [key: string]: string } | null;
  correct_choices_map?: { [key: string]: string } | null;
  incorrect_choices_map?: { [key: string]: string } | null;
  answer?: string | string[] | null;
  correct_choice?: string | null;
  submitted_answer?: string | string[] | null;
  user_choice?: string | null;
  student_subjective_answer?: string | null;
  is_correct?: boolean | null;
  manual_score?: number | null;
  teacher_comment?: string | null;
  standard_answer_text?: string | null;
  is_graded?: boolean;
}

export type PaperQuestionInternalDetail = PaperAdminQuestionDetailView;

export interface PaperAdminDetailView extends PaperAdminView {
  paper_questions: PaperAdminQuestionDetailView[];
  questions_details?: PaperAdminQuestionDetailView[];
  submitted_answers_card?: (string | null)[] | null;
}

export type PaperFullDetailModel = PaperAdminDetailView;

export interface LibraryQuestionItem {
  id?: string | number | null;
  body: string;
  question_type?: QuestionTypeEnum | string;
  choices?: { [key: string]: string } | null;
  answer?: string | string[];
  correct_choices?: string[];
  incorrect_choices?: string[];
  tags?: string[] | null;
}

export type AdminBankQuestion = LibraryQuestionItem;
export type QuestionModel = LibraryQuestionItem;

export interface AddQuestionPayload {
  body: string;
  question_type?: QuestionTypeEnum | string;
  correct_choices: string[];
  incorrect_choices: string[];
}

export interface LibraryInfo {
  id: DifficultyLevel;
  display_name: string;
  description?: string | null;
}

export interface LibraryData extends LibraryInfo {
  questions: LibraryQuestionItem[];
}

export type QuestionBankResponse = LibraryData;

export interface LibraryCreatePayload {
  id: DifficultyLevel;
  display_name: string;
  description?: string | null;
  questions?: LibraryQuestionItem[];
}

export interface LibraryUpdatePayload {
  display_name?: string | null;
  description?: string | null;
  questions: LibraryQuestionItem[];
}

export interface LibraryIndexItem extends LibraryInfo {
  question_count: number;
}

export interface AdminUserView extends UserPublicProfile {
  created_at?: string;
  last_login_at?: string;
}

export type AdminUpdateUserPayload = AdminUserUpdate;

export interface SettingsResponseModel {
  app_name?: string;
  [key: string]: any;
}

export interface SettingsUpdatePayload {
  app_name?: string;
  [key: string]: any;
}

export interface PendingGradingPaperItem {
  paper_id: string;
  user_uid: string;
  difficulty: DifficultyLevel;
  submission_time_utc?: string | null;
  pending_manual_grading_count: number;
}

export interface SubjectiveQuestionForGrading {
  question_internal_id: string;
  body: string;
  question_type: QuestionTypeEnum | string;
  student_subjective_answer?: string | null;
  standard_answer_text?: string | null;
  max_score?: number;
  manual_score?: number | null;
  teacher_comment?: string | null;
}

export interface GradeSubmissionPayload {
  score: number;
  comment?: string | null;
}

export interface AdminTokenCreate {
  description?: string | null;
}

export interface AdminTokenCreatedResponse {
  token_id: string;
  token_secret: string;
  description?: string | null;
  created_at_utc: string;
}

export interface AdminTokenInfo {
  token_id: string;
  description?: string | null;
  created_at_utc: string;
  last_used_utc?: string | null;
}

export interface SubjectiveStats {
  total_subjective_questions: number;
  graded_subjective_questions: number;
  pending_manual_grading_count: number;
}
