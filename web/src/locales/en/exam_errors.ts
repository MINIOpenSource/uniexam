
export const translations = {
  'error.fetchExam.rateLimit': 'Request frequency is too high, please try again later',
  'error.fetchExam.generic': 'An unknown network or server error occurred while fetching the exam',
  'error.fetchExam.network': 'Network error: Unable to connect to the server. Please check your network connection or try again later',
  'error.fetchExam.invalidData': 'The received exam data format is incorrect or empty',
  'error.fetchExam.fail': 'Failed to fetch exam: {status}',
  'error.fetchExam.apiError': '{message}',
  'exam_errors.toast.noDifficulty.title': 'Error Starting Exam',
  'exam_errors.toast.noDifficulty.description': 'Please select a difficulty before starting an exam.',

  'error.submit.rateLimit': 'Submission frequency is too high, please try again later',
  'error.submit.generic': 'An unknown network or server error occurred during submission',
  'error.submit.network': 'Network error during submission: Unable to connect to the server',
  'error.submit.fail': 'Submission failed: {status}',
  'error.submit.noResponse': 'Failed to receive a response from the server',
  'error.submit.unknownResponse': 'Received an unknown server response: {statusCode}',
  'error.submit.apiError': '{message}',
  'error.submit.notFound': 'Exam paper not found on the server',
  'error.submit.alreadyGraded': 'This exam paper has already been submitted and graded',
  'error.submit.invalidSubmission': 'The submitted answers are invalid (e.g., incorrect number of answers)',

  'examForm.error.noResponse': 'Failed to receive a server response',
  'examForm.error.unknownResponse': 'Received an unknown server response: {statusCode}',
  'examForm.error.networkOrServer': 'A network or server error occurred during submission',
};
