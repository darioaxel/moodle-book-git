"""GitProvider (interfaz) + LocalGitProvider (GitPython): worktrees aislados, tags, diffs."""

from courseascode.git.diff import BookDiff, Diff, FileChange
from courseascode.git.local_provider import LocalGitProvider
from courseascode.git.provider import GitProvider, GitProviderError
from courseascode.git.versioning import VersionResolver, detect_source

__all__ = [
    "BookDiff",
    "Diff",
    "FileChange",
    "GitProvider",
    "GitProviderError",
    "LocalGitProvider",
    "VersionResolver",
    "detect_source",
]
