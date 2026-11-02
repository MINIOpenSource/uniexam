
import { translations as commonTranslations } from './common';
import { translations as authTranslations } from './auth';
import { translations as examMainTranslations } from './exam_main';
import { translations as examResultTranslations } from './exam_result';
import { translations as examErrorsTranslations } from './exam_errors';
import { translations as examFeedbackTranslations } from './exam_feedback';
import { translations as adminCommonTranslations } from './admin_common';
import { translations as adminPapersTranslations } from './admin_papers';
import { translations as adminPapersDialogTranslations } from './admin_papers_dialog';
import { translations as adminPapersFilterTranslations } from './admin_papers_filter';
import { translations as adminQBankListTranslations } from './admin_qbank_list';
import { translations as adminQbmUiTranslations } from './admin_qbm_ui';
import { translations as adminQbmMessagesTranslations } from './admin_qbm_messages';
// Removed: import { translations as brandTranslations } from './brand';

export const esTranslations = {
  // ...brandTranslations, // Removed
  ...commonTranslations,
  ...authTranslations,
  ...examMainTranslations,
  ...examResultTranslations,
  ...examErrorsTranslations,
  ...examFeedbackTranslations,
  ...adminCommonTranslations,
  ...adminPapersTranslations,
  ...adminPapersDialogTranslations,
  ...adminPapersFilterTranslations,
  ...adminQBankListTranslations,
  ...adminQbmUiTranslations,
  ...adminQbmMessagesTranslations,
};
