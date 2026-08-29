from datetime import datetime, timedelta, timezone
import httpx
import respx
from radar.connectors.github import GitHubConnector

@respx.mock
def test_mocked_github_flow():
    repo={"node_id":"n1","full_name":"o/r","html_url":"https://github.com/o/r","topics":["voice-ai"],"stargazers_count":2,"fork":False}
    respx.get("https://api.github.com/repos/o/r").mock(return_value=httpx.Response(200,json=repo))
    issue={"id":1,"updated_at":datetime.now(timezone.utc).isoformat(),"title":"WebRTC voice issue","body":"realtime voice agent WebRTC","html_url":"https://github.com/o/r/issues/1","user":{"login":"dev","html_url":"https://github.com/dev"}}
    respx.get("https://api.github.com/repos/o/r/issues").mock(return_value=httpx.Response(200,json=[issue]))
    respx.get("https://api.github.com/repos/o/r/commits").mock(return_value=httpx.Response(200,json=[]))
    result=GitHubConnector().collect(datetime.now(timezone.utc)-timedelta(days=1),{"watchlist":["o/r"],"queries":[]})
    assert len(result)==1 and result[0].actor_handle=="dev" and result[0].repository_name=="o/r"
