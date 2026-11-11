"""Poker table presentation; the two rule variants stay in games_pkg.balatro."""
from boardgames.registry import GamePackage, register

register(GamePackage(name="balatro", label="小丑牌", rules="games_pkg.balatro:BalatroGame",
                     web_js="boardgames.jokers.web:WEB_JS", web_css="boardgames.jokers.web:WEB_CSS"))
