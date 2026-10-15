"""MoodleProvider (interfaz) + MoodleRestClient (httpx) contra el plugin local_courseascode."""

from courseascode.moodle.fake import FakeMoodleProvider
from courseascode.moodle.functions import PLUGIN_FUNCTIONS, PluginFunction
from courseascode.moodle.provider import (
    DeployRecord,
    MoodleCourse,
    MoodleError,
    MoodleProvider,
    RemoteBook,
    RemoteChapter,
)
from courseascode.moodle.rest_client import MoodleRestClient, RetryPolicy

__all__ = [
    "PLUGIN_FUNCTIONS",
    "DeployRecord",
    "FakeMoodleProvider",
    "MoodleCourse",
    "MoodleError",
    "MoodleProvider",
    "MoodleRestClient",
    "PluginFunction",
    "RemoteBook",
    "RemoteChapter",
    "RetryPolicy",
]
