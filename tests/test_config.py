import pytest

from timebot.config import ConfigError, _parse_milestones, load_config


def test_milestones_are_parsed_and_sorted():
    milestones = _parse_milestones("100h=Veteran, 10h=Regular,30m:Newcomer")
    assert [(m.seconds, m.role_name) for m in milestones] == [
        (1800, "Newcomer"),
        (36000, "Regular"),
        (360000, "Veteran"),
    ]


def test_milestone_role_names_may_contain_spaces():
    assert _parse_milestones("500h=Voice Gremlin")[0].role_name == "Voice Gremlin"


@pytest.mark.parametrize("raw", ["10h", "10h=", "banana=Role", "=Role"])
def test_bad_milestones_are_rejected(raw):
    with pytest.raises(ConfigError):
        _parse_milestones(raw)


def test_empty_milestones(monkeypatch):
    assert _parse_milestones("") == ()
    assert _parse_milestones(None) == ()


def test_missing_token_is_a_config_error(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    with pytest.raises(ConfigError, match="DISCORD_TOKEN"):
        load_config()


def test_placeholder_token_is_rejected(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "YourTokenHere")
    with pytest.raises(ConfigError, match="placeholder"):
        load_config()


def test_config_reads_the_environment(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "abc.def.ghi")
    monkeypatch.setenv("GUILD_IDS", "123, 456")
    monkeypatch.setenv("EXCLUDED_CHANNEL_IDS", "789")
    monkeypatch.setenv("IGNORE_DEAFENED", "false")
    monkeypatch.setenv("MILESTONES", "1h=Rookie")
    monkeypatch.setenv("TIMEZONE", "Europe/Berlin")

    config = load_config()
    assert config.guild_ids == (123, 456)
    assert config.excluded_channel_ids == frozenset({789})
    assert config.ignore_deafened is False
    assert config.milestones_enabled is True
    assert str(config.timezone) == "Europe/Berlin"


def test_invalid_values_are_rejected(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "abc")
    monkeypatch.setenv("DIGEST_WEEKDAY", "9")
    with pytest.raises(ConfigError, match="DIGEST_WEEKDAY"):
        load_config()
