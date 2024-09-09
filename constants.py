from enum import Enum

# level-2 user constants
SQLITE_DB_PATH = "automator.db"
VIEWPORT = {'width': 600, 'height': 200}

# level-3 user constants
PROGRESS_SUFFIX = "_progress"
BREAK_LINE = '-' * 40
SHEETS_DOMAIN = "https://docs.google.com/spreadsheets/d/"
SHEETS_EXPORT_PARAM = "/export?gid=0&format=csv"
LINKEDIN_LEARNING_URL = "https://www.linkedin.com/learning/"
APPROX_COURSE_DURATION_HOURS = 3
MAX_RETRIES = 3
RETRY_SLEEP = 17
QUICK_TOGGLE_SCREEN_SLEEP = 5
OPEN_TAB_SLEEP = 5
SWITCH_TO_LAST_COURSE_MINUTES = 10 * 60


class SheetHeader(Enum):
    URL, CERTIFIED, ATTEMPT, MAX_ATTEMPT = "url", "certified", "attempt", "max_attempt"


class Status(Enum):
    IN_PROGRESS, YES, NO = 'InProgress', 'Yes', 'No'


class Tab:
    def __init__(self, tab, last_course=None, resume_time=0):
        self.tab = tab
        self.last_course = last_course
        self.resume_time = resume_time
