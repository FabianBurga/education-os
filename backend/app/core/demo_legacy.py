"""Cookie transport for the four existing persona consoles; normal HTML unchanged."""

from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.core.config import settings


def console_response(path: Path, request: Request):
    source = path.read_text(encoding="utf-8")
    if settings.EDUCATION_OS_DEMO_MODE:
        # Auth is performed by the demo middleware before any legacy HTML is served.
        source = source.replace(
            "<head>",
            """<head><script>
window.educationDemo=true;
function exitDemoView(){document.body.replaceChildren();location.replace('/app/');}
new BroadcastChannel('education-demo-session').onmessage=exitDemoView;
window.addEventListener('pageshow',event=>{if(event.persisted)exitDemoView();});
setTimeout(exitDemoView,900000);
</script><style>.auth{display:none!important}</style>""",
        )
        source = source.replace("<main>", '<main><a href="/app/">Volver a Education OS</a>')
        for variable in ("tokenEl", "studentTokenEl", "guardianToken"):
            source = source.replace(
                f"{variable}.value=sessionStorage",
                f"{variable}.value=window.educationDemo?'':sessionStorage",
            )
            source = source.replace(
                f"if(!{variable}.value.trim())",
                f"if(!window.educationDemo&&!{variable}.value.trim())",
            )
            source = source.replace(
                f"if({variable}.value.trim())", f"if(window.educationDemo||{variable}.value.trim())"
            )
            source = source.replace(
                f"if(window.educationDemo||{variable}.value.trim()) h.Authorization",
                f"if(!window.educationDemo&&{variable}.value.trim()) h.Authorization",
            )
    return HTMLResponse(source)
