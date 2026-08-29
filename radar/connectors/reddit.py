from datetime import datetime, timezone
import httpx
from .base import ConnectorAdapter
from .http import ResilientClient
from ..models import Intent
from ..schemas import NormalizedSignal


class RedditConnector(ConnectorAdapter):
    name="reddit"
    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        token=httpx.post("https://www.reddit.com/api/v1/access_token",auth=(client_id,client_secret),data={"grant_type":"client_credentials"},headers={"User-Agent":user_agent},timeout=20).json()["access_token"]
        self.http=ResilientClient({"Authorization":f"Bearer {token}","User-Agent":user_agent})
    def collect(self, since, config):
        out=[]
        for sub in config.get("subreddits",["LocalLLaMA","LanguageTechnology"]):
            for query in config.get("queries",["voice AI","speech-to-text"]):
                data=self.http.get(f"https://oauth.reddit.com/r/{sub}/search",params={"q":query,"restrict_sr":1,"sort":"new","limit":50}).json()
                for child in data.get("data",{}).get("children",[]):
                    a=child["data"]; at=datetime.fromtimestamp(a["created_utc"],timezone.utc)
                    if at<since: continue
                    url="https://www.reddit.com"+a["permalink"]; text=(a.get("selftext") or a["title"])[:500]
                    out.append(NormalizedSignal(source="reddit",external_id=a["name"],canonical_url=url,actor_handle=a["author"],actor_profile_url=f"https://www.reddit.com/user/{a['author']}",observed_intent=Intent.COMMUNITY_DISCUSSION,intent_evidence=text,activity_type="post",activity_title=a["title"],activity_text=text,activity_at=at,discovery_query=f"r/{sub}:{query}",collected_at=datetime.now(timezone.utc),raw_metadata={"subreddit":sub}))
        return out

