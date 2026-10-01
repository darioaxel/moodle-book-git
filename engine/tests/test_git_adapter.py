"""Tests del Git adapter y el VersionResolver (ENG-020-026)."""

from __future__ import annotations

from pathlib import Path

import pytest

from courseascode.domain import RefKind
from courseascode.git import (
    GitProviderError,
    LocalGitProvider,
    VersionResolver,
    detect_source,
)

SHA_LEN = 40
JUAN_COMMITS_AHEAD = 3
MAIN_COMMITS_AHEAD = 2


@pytest.fixture()
def provider(git_repo: Path) -> LocalGitProvider:
    return LocalGitProvider(git_repo)


class TestLocalGitProvider:
    def test_get_ref_tipos(self, provider: LocalGitProvider) -> None:
        assert provider.get_ref("book/ut03-mvc/v1.0.0").kind is RefKind.TAG
        assert provider.get_ref("main").kind is RefKind.BRANCH
        sha = provider.get_commit("main")
        assert provider.get_ref(sha[:7]).kind is RefKind.COMMIT

    def test_get_ref_inexistente(self, provider: LocalGitProvider) -> None:
        with pytest.raises(GitProviderError, match="no encontrada"):
            provider.get_ref("rama-imposible")

    def test_get_file(self, provider: LocalGitProvider) -> None:
        content = provider.get_file("book/ut03-mvc/v1.0.0", "course.yml")
        assert "id: dwes" in content

    def test_get_file_inexistente(self, provider: LocalGitProvider) -> None:
        with pytest.raises(GitProviderError, match="no encontrado"):
            provider.get_file("main", "books/no-existe.md")

    def test_list_files(self, provider: LocalGitProvider) -> None:
        files = provider.list_files("book/ut03-mvc/v1.0.0", "books/ut03-mvc")
        assert "books/ut03-mvc/02-mvc.md" in files
        assert "books/ut03-mvc/assets/mvc.svg" in files
        assert "books/ut03-mvc/06-observer.md" not in files

    def test_get_commit_peela_tags(self, provider: LocalGitProvider) -> None:
        sha = provider.get_commit("book/ut03-mvc/v1.2.0")
        assert len(sha) == SHA_LEN
        assert provider.get_commit("main") != sha

    def test_list_tags_glob(self, provider: LocalGitProvider) -> None:
        assert provider.list_tags("book/ut03-mvc/v*") == [
            "book/ut03-mvc/v1.0.0",
            "book/ut03-mvc/v1.1.0",
            "book/ut03-mvc/v1.2.0",
        ]
        assert provider.list_tags() == [
            "book/ut03-mvc/v1.0.0",
            "book/ut03-mvc/v1.1.0",
            "book/ut03-mvc/v1.2.0",
            "book/ut04-dao/v1.0.0",
        ]

    def test_diff(self, provider: LocalGitProvider) -> None:
        diff = provider.diff("book/ut03-mvc/v1.0.0", "book/ut03-mvc/v1.2.0")
        by_path = {c.path: c.status for c in diff.changes}
        assert by_path["books/ut03-mvc/06-observer.md"] == "added"
        assert by_path["books/ut03-mvc/02-mvc.md"] == "modified"
        assert by_path["books/ut03-mvc/03-model.md"] == "modified"
        assert not any(c.status == "deleted" for c in diff.changes)

    def test_diff_for_book_clasifica(self, provider: LocalGitProvider) -> None:
        diff = provider.diff("book/ut03-mvc/v1.0.0", "book/ut03-mvc/v1.2.0")
        book_diff = diff.for_book(
            "books/ut03-mvc",
            chapter_files={
                "01-introduccion.md",
                "02-mvc.md",
                "03-model.md",
                "04-view.md",
                "05-controller.md",
                "06-observer.md",
            },
        )
        assert book_diff.added_chapters == ("06-observer.md",)
        assert set(book_diff.modified_chapters) == {"02-mvc.md", "03-model.md"}
        assert book_diff.deleted_chapters == ()
        assert len(book_diff.other) == 1  # book.yml modificado

    def test_merge_base(self, provider: LocalGitProvider) -> None:
        assert provider.merge_base("main", "juan") == provider.get_commit("book/ut03-mvc/v1.2.0")

    def test_commits_ahead(self, provider: LocalGitProvider) -> None:
        base = provider.merge_base("main", "juan")
        assert provider.commits_ahead(base, "juan") == JUAN_COMMITS_AHEAD
        assert provider.commits_ahead(base, "main") == MAIN_COMMITS_AHEAD

    def test_is_ancestor(self, provider: LocalGitProvider) -> None:
        assert provider.is_ancestor("book/ut03-mvc/v1.1.0", "book/ut03-mvc/v1.2.0")
        assert not provider.is_ancestor("book/ut03-mvc/v1.2.0", "book/ut03-mvc/v1.1.0")

    def test_checkout_ref_aislado(self, provider: LocalGitProvider, git_repo: Path) -> None:
        with provider.checkout_ref("book/ut03-mvc/v1.0.0") as worktree:
            assert not (worktree / "books/ut03-mvc/06-observer.md").exists()
            assert (worktree / "books/ut03-mvc/02-mvc.md").is_file()
            # anidado: dos worktrees simultáneos
            with provider.checkout_ref("juan") as other:
                assert (other / "books/ut03-mvc/07-extra.md").is_file()
        # el working tree del usuario no se ha tocado
        assert (git_repo / "books/ut03-mvc/06-observer.md").is_file()

    def test_checkout_ref_invalido(self, provider: LocalGitProvider) -> None:
        with pytest.raises(GitProviderError), provider.checkout_ref("ref-imposible"):
            pass

    def test_current_branch(self, provider: LocalGitProvider) -> None:
        assert provider.current_branch() == "main"
        with (
            pytest.raises(GitProviderError, match="desacoplado"),
            provider.checkout_ref("main") as wt,
        ):
            LocalGitProvider(wt).current_branch()


class TestVersionResolver:
    def test_versions_for_ordenadas(self, provider: LocalGitProvider) -> None:
        resolver = VersionResolver(provider)
        versions = resolver.versions_for("ut03-mvc")
        assert [str(v) for _, v in versions] == ["1.0.0", "1.1.0", "1.2.0"]

    def test_latest(self, provider: LocalGitProvider) -> None:
        resolver = VersionResolver(provider)
        latest = resolver.latest("ut03-mvc")
        assert latest is not None
        tag, version = latest
        assert tag == "book/ut03-mvc/v1.2.0"
        assert str(version) == "1.2.0"
        assert resolver.latest("ut05-sin-tags") is None

    def test_version_derivada_rama_personal(self, provider: LocalGitProvider) -> None:
        """DoD Fase 2: juan = 1.2.0+juan.3 con 3 commits propios."""
        resolver = VersionResolver(provider)
        derived = resolver.derived_version("ut03-mvc", branch="juan")
        assert str(derived) == "1.2.0+juan.3"

    def test_version_derivada_main_sin_divergencia(self, provider: LocalGitProvider) -> None:
        resolver = VersionResolver(provider)
        derived = resolver.derived_version("ut03-mvc", branch="main")
        assert str(derived) == "1.2.0+main.0"

    def test_version_derivada_sin_tags_base(self, provider: LocalGitProvider) -> None:
        resolver = VersionResolver(provider)
        derived = resolver.derived_version("ut05-sin-tags", branch="juan")
        assert str(derived) == "0.0.0+juan.3"

    def test_detect_source(self, provider: LocalGitProvider) -> None:
        assert detect_source(provider) == "main"
