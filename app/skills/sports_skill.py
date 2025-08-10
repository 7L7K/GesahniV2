# app/skills/sports_skill.py
from __future__ import annotations

import re

import httpx

from .base import Skill


WIN_PATTERN = re.compile(r"did the (?P<team>[\w\s]+) win", re.I)
NEXT_PATTERN = re.compile(r"next game for (?P<team>[\w\s]+)", re.I)


class SportsSkill(Skill):
    PATTERNS = [WIN_PATTERN, NEXT_PATTERN]

    async def run(self, prompt: str, match: re.Match) -> str:
        team = match.group("team").strip()
        async with httpx.AsyncClient(timeout=5.0) as client:
            search = await client.get(
                "https://www.thesportsdb.com/api/v1/json/3/searchteams.php",
                params={"t": team},
            )
            search.raise_for_status()
            data = search.json()
            teams = data.get("teams")
            if not teams:
                return f"I couldn't find a team named {team}."
            team_info = teams[0]
            team_id = team_info["idTeam"]
            team_name = team_info["strTeam"]

            if match.re is WIN_PATTERN:
                last_resp = await client.get(
                    "https://www.thesportsdb.com/api/v1/json/3/eventslast.php",
                    params={"id": team_id},
                )
                last_resp.raise_for_status()
                results = last_resp.json().get("results")
                if not results:
                    return f"No recent games found for {team_name}."
                last = results[0]
                home = last["strHomeTeam"]
                away = last["strAwayTeam"]
                home_score = last["intHomeScore"]
                away_score = last["intAwayScore"]
                if home_score is None or away_score is None:
                    return f"No score data found for {team_name}."
                home_score = int(home_score)
                away_score = int(away_score)
                if home == team_name:
                    win = home_score > away_score
                    opponent = away
                    team_score = home_score
                    opp_score = away_score
                else:
                    win = away_score > home_score
                    opponent = home
                    team_score = away_score
                    opp_score = home_score
                result = "won" if win else "lost"
                return (
                    f"The {team_name} {result} {team_score}-{opp_score} against the {opponent}."
                )

            next_resp = await client.get(
                "https://www.thesportsdb.com/api/v1/json/3/eventsnext.php",
                params={"id": team_id},
            )
            next_resp.raise_for_status()
            events = next_resp.json().get("events")
            if not events:
                return f"No upcoming games found for {team_name}."
            nxt = events[0]
            home = nxt["strHomeTeam"]
            away = nxt["strAwayTeam"]
            opponent = away if home == team_name else home
            date = nxt.get("dateEvent")
            time = nxt.get("strTime")
            return (
                f"The next game for the {team_name} is against the {opponent} on {date} at {time}."
            )
