# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""
Global schema configuration.
"""

import mashumaro

__all__ = ["GlobalSchemaConfig"]


class GlobalSchemaConfig(mashumaro.config.BaseConfig):
    forbid_extra_keys = True
    omit_default = True
