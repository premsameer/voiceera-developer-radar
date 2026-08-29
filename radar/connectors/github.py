from datetime import datetime, timezone
from .base import ConnectorAdapter
from .http import ResilientClient
from ..models import Intent
from ..schemas import NormalizedSignal


def _dt(value: str) -> datetime: return datetime.fromisoformat(value.replace("Z", "+00:00"))


class GitHubConnector(ConnectorAdapter):
    name = "github"
    def __init__(self, token: str | None = None):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token: headers["Authorization"] = f"Bearer {token}"
        self.http = ResilientClient(headers)

    def collect(self, since: datetime, config: dict) -> list[NormalizedSignal]:
        signals = []
        repos = set(config.get("watchlist", []))
        for query in config.get("queries", []):
            q = f"{query} pushed:>={since.date().isoformat()} archived:false"
            data = self.http.get("https://api.github.com/search/repositories", params={"q": q, "per_page": config.get("per_page", 10)}).json()
            repos.update(item["full_name"] for item in data.get("items", []))
        for repo in list(repos)[: config.get("max_repositories", 25)]:
            signals.extend(self._repo_activity(repo, since, config))
        return signals

    def _repo_activity(self, repo: str, since: datetime, config: dict):
        out = []
        repo_data = self.http.get(f"https://api.github.com/repos/{repo}").json()
        topics = repo_data.get("topics", [])
        events = [
            ("issues", self.http.get(f"https://api.github.com/repos/{repo}/issues", params={"state":"all","since":since.isoformat(),"per_page":30}).json()),
            ("commits", self.http.get(f"https://api.github.com/repos/{repo}/commits", params={"since":since.isoformat(),"per_page":30}).json()),
        ]
        for kind, items in events:
            if not isinstance(items, list): continue
            for item in items:
                if kind == "issues":
                    actor=item.get("user") or {}; is_pr="pull_request" in item; activity="pull_request" if is_pr else "issue"
                    updated=_dt(item["updated_at"]); title=item.get("title", ""); excerpt=(item.get("body") or title)[:500]
                    ext=f"{activity}:{item['id']}"; url=item["html_url"]
                    intent=Intent.CONTRIBUTING if is_pr else Intent.TROUBLESHOOTING
                else:
                    actor=item.get("author") or {}; commit=item.get("commit") or {}; message=(commit.get("message") or "").splitlines()[0]
                    updated=_dt((commit.get("author") or {}).get("date")); title=message; excerpt=message[:500]
                    ext=f"commit:{item['sha']}"; url=item["html_url"]; activity="commit"; intent=Intent.CONTRIBUTING
                if updated < since or not actor.get("login"): continue
                out.append(NormalizedSignal(source="github", external_id=ext, canonical_url=url,
                    actor_handle=actor["login"], actor_display_name=None, actor_profile_url=actor.get("html_url"),
                    observed_intent=intent, intent_evidence=excerpt, activity_type=activity, activity_title=title,
                    activity_text=excerpt, activity_at=updated, repository_name=repo, repository_url=repo_data["html_url"],
                    repository_topics=topics, programming_languages=[], discovery_query="watchlist/search",
                    collected_at=datetime.now(timezone.utc), raw_metadata={"github_node_id":repo_data.get("node_id"),"stars":repo_data.get("stargazers_count",0),"fork":repo_data.get("fork",False)}))
        return out

