"""Shared local UI theme; analysis and detector state remain outside this module."""

STYLES = """<style>
:root{--vf-ink:#183044;--vf-muted:#6d7f91;--vf-teal:#087f86;--vf-line:#e1e8ef}
.stApp{background:#f1f5f9;color:var(--vf-ink)}
[data-testid="stHeader"],[data-testid="stToolbar"],footer{display:none}
.block-container{max-width:1450px;padding:24px 32px 28px}
[data-testid="stVerticalBlock"]{gap:1rem}
h1,h2,h3{color:var(--vf-ink);letter-spacing:-.035em}
h2{font-size:1.65rem!important}h3{font-size:1.2rem!important}
p,[data-testid="stCaptionContainer"]{line-height:1.6}
[data-testid="stCaptionContainer"]{color:var(--vf-muted)}
.vf-masthead{display:flex;align-items:center;justify-content:space-between;gap:24px;background:#122e42;color:#fff;border-radius:18px;padding:18px 24px;box-shadow:0 8px 24px #122e4210}
.vf-brand{display:flex;align-items:center;gap:14px}.vf-mark{width:46px;height:46px;display:grid;place-items:center;border-radius:13px;background:#137e87;flex:none}
.vf-mark svg{width:30px;height:30px}.vf-masthead h1{font-family:inherit;font-size:27px!important;font-weight:750;letter-spacing:-1px;color:white;padding:0!important;margin:0!important;line-height:1.15!important}
.vf-masthead p{font-size:12px;color:#c2d4df;margin:4px 0 0;line-height:1.5}.vf-header-tags{display:flex;align-items:center;gap:10px;white-space:nowrap}
.vf-local{font-size:11px;color:#b9d1df;display:flex;align-items:center;gap:6px}.vf-local svg{width:14px;height:14px}
.vf-demo{font-size:10px;letter-spacing:.09em;border:1px solid #5b7b8d;color:#d4e6ee;border-radius:6px;padding:5px 8px;font-weight:650}
[data-testid="stRadio"] [role="radiogroup"]{gap:4px;padding:4px;background:#e5edf3;border:1px solid #dde6ee;border-radius:11px;width:fit-content}
[data-testid="stRadio"] label{margin:0!important;padding:7px 13px!important;border-radius:8px;transition:background .15s;color:#5b7185}
[data-testid="stRadio"] label:has(input:checked){background:#fff;color:#126b76;box-shadow:0 1px 4px #17364c12}
[data-testid="stRadio"] label p{font-size:13px;font-weight:600}
[data-testid="stRadio"] label:focus-within{outline:2px solid #51aeb7;outline-offset:1px}
[data-testid="stMetric"]{background:white;border:1px solid var(--vf-line);border-radius:14px;padding:16px 20px}
[data-testid="stMetricLabel"] p{color:var(--vf-muted);font-size:12px!important}
[data-testid="stMetricValue"]{font-size:1.8rem;letter-spacing:-.04em;color:var(--vf-ink)}
[data-testid="stFileUploader"]{border:1px solid var(--vf-line);border-radius:16px;background:white;padding:20px}
[data-testid="stFileUploaderDropzone"]{border:1px dashed #9cbfc9;border-radius:12px;background:#f5fafb;padding:28px 20px}
div.stButton>button,div.stDownloadButton>button{border-radius:10px;border-color:#d6e1e9;font-weight:600;font-size:13px;min-height:42px}
div.stButton>button[kind="primary"]{background:#087f86;border-color:#087f86;padding-left:24px;padding-right:24px}
div.stButton>button:hover,div.stDownloadButton>button:hover{border-color:#36949e;color:#087f86}
div.stButton>button[kind="primary"]:hover{background:#066870;color:white}
[data-testid="stExpander"]{border:1px solid var(--vf-line);background:white;border-radius:12px;overflow:hidden}
[data-testid="stDataFrame"],video{border-radius:12px;overflow:hidden}
.vf-section-kicker{font-size:10px;font-weight:750;letter-spacing:.12em;color:#087f86;margin:10px 0 5px}
.vf-section-title{font-size:25px;font-weight:740;letter-spacing:-.04em;margin:0 0 5px;padding:0!important;line-height:1.3;color:var(--vf-ink)}
.vf-section-copy{font-size:13px;color:#6b8092;margin:0 0 4px}
.vf-guide{background:#fff;border:1px solid var(--vf-line);border-radius:16px;padding:21px 22px;color:#1d3c50}
.vf-guide h3{font-size:15px!important;font-weight:700;margin:0 0 17px;letter-spacing:-.02em}
.vf-guide ol{list-style:none;counter-reset:steps;margin:0;padding:0;display:grid;gap:15px}
.vf-guide li{counter-increment:steps;position:relative;padding-left:33px;font-size:12px;line-height:1.6;color:#718495}
.vf-guide li:before{content:counter(steps);position:absolute;left:0;top:0;width:23px;height:23px;border-radius:7px;background:#edf6f5;color:#087b80;display:grid;place-items:center;font-size:11px;font-weight:700}
.vf-guide strong{display:block;font-size:12px;color:#304d62;margin-bottom:2px}
.vf-privacy{display:flex;align-items:center;gap:8px;font-size:11px;color:#66818b;margin-top:20px;padding-top:15px;border-top:1px solid #e9eff3}
.vf-privacy svg{width:17px;height:17px;color:#17858b;flex:none}
.vf-limits{font-size:11px;color:#8092a1;border-top:1px solid #dfe8ed;padding-top:12px;margin-top:8px}
@media(max-width:700px){.block-container{padding:14px 16px}.vf-masthead{padding:16px;border-radius:13px;gap:12px}.vf-header-tags{display:none}.vf-masthead p{font-size:11px}.vf-masthead h1{font-size:24px!important}.vf-mark{width:40px;height:40px}.vf-brand{gap:11px}[data-testid="stRadio"] label{padding:6px 9px!important}[data-testid="stRadio"] label p{font-size:12px}}
</style>"""


def render_header(realtime=False):
    import streamlit as st
    description = ("Demo theo dõi tư thế và cảnh báo qua webcam" if realtime
                   else "Demo phát hiện nghi té ngã trên video ghi sẵn")
    st.markdown(STYLES, unsafe_allow_html=True)
    st.markdown(f'''<header class="vf-masthead"><div class="vf-brand">
<div class="vf-mark" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><path d="M16 3 27 7v8c0 7-5 11-11 14C10 26 5 22 5 15V7Z" stroke="white" stroke-width="1.6"/><path d="M9 16h4l2-5 3 10 2-5h4" stroke="#a8f3db" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
<div><h1>VinFall<span style="color:#68c6c2" aria-hidden="true">.</span></h1><p>{description}</p></div></div>
<div class="vf-header-tags"><span class="vf-local"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="6" y="10" width="12" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg> Xử lý trên máy</span><span class="vf-demo">LOCALHOST · DEMO</span></div></header>''', unsafe_allow_html=True)


def render_upload_guide():
    import streamlit as st
    st.markdown('''<aside class="vf-guide"><h3>Một clip tốt giúp nhận diện tốt hơn</h3><ol>
<li><strong>Một người, camera cố định</strong>Thấy rõ toàn thân và vùng sàn trong suốt video.</li>
<li><strong>Có tư thế đứng ở đầu clip</strong>Giữ người trong khung để hiệu chuẩn trong 2–3 giây đầu.</li>
<li><strong>Xem lại trước khi kết luận</strong>Đối chiếu cảnh báo với video và thời điểm sự kiện.</li></ol>
<div class="vf-privacy"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m12 3 8 3v6c0 5-4 8-8 10-4-2-8-5-8-10V6Z"/><path d="m8 12 3 3 5-6"/></svg>Video được phân tích cục bộ trên máy này.</div></aside>''', unsafe_allow_html=True)
