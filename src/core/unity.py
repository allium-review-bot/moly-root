"""The Unity version UnityPy falls back to, and the single place that sets it.

Every extractor used to assign ``UnityPy.config.FALLBACK_UNITY_VERSION`` a
literal at module scope.  Extractors are imported lazily, inside the jobs that
use them, so those assignments ran *after* the command line had already been
honoured and replaced an explicit ``--unity-version`` with the literal: the run
then read every asset at a version nobody asked for, and nothing said so.  A
version mismatch does not fail loudly -- it changes how serialized objects are
laid out -- so the wrong answer looked like an answer.

Setting it is therefore conditional and lives here.  An explicit choice always
wins; a process that already configured one keeps it; only a process that never
chose gets :data:`DEFAULT_UNITY_VERSION`.  Importing an extractor can no longer
change the version a caller selected.
"""
import UnityPy.config

#: The version assumed for assets whose bundle does not state one.
DEFAULT_UNITY_VERSION = "2022.3.62f3"


def configure_fallback_unity_version(unity_version=None):
    """Set the fallback Unity version for this process and return it.

    *unity_version* wins when given.  With ``None`` an already-configured value
    is kept, so a lazily imported extractor cannot overwrite the caller's
    choice, and the default applies only to a wholly unconfigured process.
    """
    if unity_version:
        UnityPy.config.FALLBACK_UNITY_VERSION = unity_version
    elif not getattr(UnityPy.config, "FALLBACK_UNITY_VERSION", None):
        UnityPy.config.FALLBACK_UNITY_VERSION = DEFAULT_UNITY_VERSION
    return UnityPy.config.FALLBACK_UNITY_VERSION
