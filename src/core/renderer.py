"""Renderer state shared by geometry exporters, independent of shader passes."""


def shadow_casting_mode(renderer):
    """Unity Renderer.m_CastShadows, not a boolean or material property.

    UnityCsReference Runtime/Export/Graphics/GraphicsEnums.cs:1348-1354:
    Off=0, On=1, TwoSided=2, ShadowsOnly=3. Do not invent a value when the
    serialized renderer lacks this field; callers must expose that source gap.
    """
    mode = renderer["m_CastShadows"]
    if type(mode) is not int or mode not in (0, 1, 2, 3):
        raise ValueError(f"unsupported Renderer.m_CastShadows: {mode!r}")
    return mode


MISSING_CAST_SHADOWS = "renderer does not serialize m_CastShadows"


def shadow_casting_mode_or_gap(renderer):
    """``(mode, gap)``: the mode, or ``None`` and why it could not be read.

    For the callers the strict reader above tells to expose a source gap.
    A geometry exporter is one of them: dropping a package because a single
    renderer omits a single field loses the geometry *and* the fact. The
    mode stays ``None`` -- nothing is invented, and a consumer can tell it
    apart from 0, which is a real mode (Off).
    """
    if "m_CastShadows" not in renderer:
        return None, MISSING_CAST_SHADOWS
    try:
        return shadow_casting_mode(renderer), None
    except ValueError as exc:
        return None, str(exc)
