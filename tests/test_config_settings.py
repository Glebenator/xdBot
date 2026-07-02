import config


def test_settings_object_loads() -> None:
    assert config.settings is not None
    assert isinstance(config.settings.prefix, str)


def test_music_defaults_are_valid() -> None:
    assert config.settings.music_max_queue_size > 0
    assert config.settings.music_idle_timeout > 0
    assert 0.0 <= config.settings.music_default_volume <= 1.0
    assert config.settings.music_max_duration > 0
