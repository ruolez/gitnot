"""Site-wide settings an admin changes in the browser."""

from flask import Blueprint, jsonify

import db
from auth import admin_required
from util import api_error, audit, body

bp = Blueprint("site_settings", __name__, url_prefix="/api/admin/settings")

# key: (default, parser returning the stored string or raising ValueError)
def _int_range(lo, hi):
    def parse(v):
        n = int(v)
        if not lo <= n <= hi:
            raise ValueError(f"must be {lo}-{hi}")
        return str(n)
    return parse


def _flag(v):
    if not isinstance(v, bool):
        raise ValueError("must be true or false")
    return "1" if v else "0"


SETTINGS = {
    "max_file_mb": ("100", _int_range(0, 10240)),
    "max_asset_mb": ("2048", _int_range(1, 102400)),
    "allow_internal_remotes": ("0", _flag),
}


def current():
    out = {}
    for key, (default, parse) in SETTINGS.items():
        raw = db.get_setting(key, default)
        out[key] = raw == "1" if parse is _flag else int(raw)
    return out


@bp.get("")
@admin_required
def get_settings():
    return jsonify(current())


@bp.patch("")
@admin_required
def update_settings():
    data = body()
    for key, value in data.items():
        if key not in SETTINGS:
            return api_error(f"Unknown setting {key}")
        try:
            stored = SETTINGS[key][1](value)
        except (TypeError, ValueError) as e:
            return api_error(f"{key} {e}")
        db.set_setting(key, stored)
    audit("settings.updated", {"keys": sorted(data)})
    return jsonify(current())
