from urllib.parse import quote, urlencode

from app.projects.repository_standards.services.repository_compliance_service import (
    MOJ_CROWN_LOGO,
)


def get_technical_standard_badge_svg(compliant: bool) -> str:
        if compliant:
                message = "COMPLIANT"
                color = "cce2d8"
                text_color = "005a30"
        else:
                message = "NON-COMPLIANT"
                color = "f4cdc6"
                text_color = "2a0b06"

        label_width = 64
        status_width = 136
        badge_width = label_width + status_width
        status_center = label_width + status_width / 2

        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{badge_width}" height="28" viewBox="0 0 {badge_width} 28" role="img" aria-label="MOJ {message}">
    <title>MOJ: {message}</title>
    <g shape-rendering="crispEdges">
        <rect width="{label_width}" height="28" fill="#0b0c0c" />
        <rect x="{label_width}" width="{status_width}" height="28" fill="#{color}" />
    </g>
    <image x="9" y="7" width="14" height="14" href="data:image/png;base64,{MOJ_CROWN_LOGO}" />
    <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
        <text x="43" y="18">MOJ</text>
        <text x="{status_center}" y="18" font-weight="bold" fill="#{text_color}">{message}</text>
    </g>
</svg>'''


def get_technical_standard_badge_shield_url(
    compliant: bool | None, style: str
) -> str:
    if compliant is True:
        message = "COMPLIANT"
        color = "cce2d8"
    elif compliant is False:
        message = "NON-COMPLIANT"
        color = "f4cdc6"
    else:
        message = "NOT FOUND"
        color = "b1b4b6"

    logo_query = urlencode({"logo": f"data:image/png;base64,{MOJ_CROWN_LOGO}"})
    return (
        f"https://img.shields.io/badge/{quote('MOJ')}-{quote(message)}-{color}"
        f"?style={style}&labelColor=0b0c0c&{logo_query}"
    )