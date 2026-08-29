from datetime import datetime, timezone
import feedparser
from .base import ConnectorAdapter
from .http import ResilientClient
from ..models import Intent
from ..schemas import NormalizedSignal


class ForemConnector(ConnectorAdapter):
    name="devto"
    def __init__(self, api_key=None): self.http=ResilientClient({"api-key":api_key} if api_key else {})
    def collect(self, since, config):
        out=[]
        for tag in config.get("tags", ["voice","webrtc","machinelearning"]):
            for a in self.http.get("https://dev.to/api/articles", params={"tag":tag,"per_page":30,"top":7}).json():
                at=datetime.fromisoformat(a["published_at"].replace("Z","+00:00"))
                if at < since: continue
                text=(a.get("description") or a["title"])[:500]; user=a["user"]
                out.append(NormalizedSignal(source="devto",external_id=str(a["id"]),canonical_url=a["canonical_url"],actor_handle=user["username"],actor_display_name=user.get("name"),actor_profile_url=f"https://dev.to/{user['username']}",observed_intent=Intent.LEARNING,intent_evidence=text,activity_type="article",activity_title=a["title"],activity_text=text,activity_at=at,discovery_query=f"tag:{tag}",collected_at=datetime.now(timezone.utc),raw_metadata={"tags":a.get("tag_list",[])}))
        return out


class HackerNewsConnector(ConnectorAdapter):
    name="hackernews"
    def __init__(self): self.http=ResilientClient()
    def collect(self, since, config):
        out=[]
        ids=self.http.get("https://hacker-news.firebaseio.com/v0/newstories.json").json()[:config.get("max_items",100)]
        for ident in ids:
            a=self.http.get(f"https://hacker-news.firebaseio.com/v0/item/{ident}.json").json() or {}
            at=datetime.fromtimestamp(a.get("time",0),timezone.utc); title=a.get("title","")
            if at<since: continue
            url=f"https://news.ycombinator.com/item?id={ident}"
            out.append(NormalizedSignal(source="hackernews",external_id=str(ident),canonical_url=url,actor_handle=a.get("by","unknown"),actor_profile_url=f"https://news.ycombinator.com/user?id={a.get('by','unknown')}",observed_intent=Intent.COMMUNITY_DISCUSSION,intent_evidence=title,activity_type="post",activity_title=title,activity_text=(a.get("text") or title)[:500],activity_at=at,discovery_query="newstories",collected_at=datetime.now(timezone.utc)))
        return out


class RSSConnector(ConnectorAdapter):
    name="rss"
    def collect(self, since, config):
        out=[]
        for feed_url in config.get("feeds",[]):
            feed=feedparser.parse(feed_url)
            for item in feed.entries:
                stamp=item.get("published_parsed") or item.get("updated_parsed")
                if not stamp: continue
                at=datetime(*stamp[:6],tzinfo=timezone.utc)
                if at<since: continue
                title=item.get("title",""); link=item.get("link")
                out.append(NormalizedSignal(source="rss",external_id=item.get("id",link),canonical_url=link,actor_handle=item.get("author","unknown"),observed_intent=Intent.COMMUNITY_DISCUSSION,intent_evidence=title,activity_type="article",activity_title=title,activity_text=item.get("summary",title)[:500],activity_at=at,discovery_query=feed_url,collected_at=datetime.now(timezone.utc)))
        return out

