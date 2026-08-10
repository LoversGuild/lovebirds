# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""Reformat participation database."""

from lovebirds.cli.config import Config


def reformat_people(config: Config) -> None:
    config.save_people()
