from collections.abc import Callable

from lovebirds.cli.config import Config
from lovebirds.cli.reformat import reformat_people


class TestReformatPeople:
    def test_calls_save(self, make_config: Callable[..., Config]) -> None:
        config = make_config()
        reformat_people(config)
        config.save_people.assert_called_once()  # type: ignore[attr-defined]
