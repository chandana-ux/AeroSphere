"""Offline chart configuration and AeroSphere workspace styling."""
import streamlit as st


def offline_chart(figure, **kwargs):
    config = kwargs.pop('config', {})
    config.update(displaylogo=False, modeBarButtonsToRemove=['sendDataToCloud', 'sendChartToCloud'])
    return st.plotly_chart(figure, config=config, **kwargs)


def apply_workspace_theme():
    st.markdown(
        """
        <style>
        :root {
            --aero-bg: #091116;
            --aero-bg-strong: #0d171c;
            --aero-panel: #111c22;
            --aero-panel-strong: #17242a;
            --aero-border: rgba(164, 187, 190, 0.16);
            --aero-border-strong: rgba(103, 217, 203, 0.42);
            --aero-text: #eef3ef;
            --aero-text-soft: #bfceca;
            --aero-text-muted: #81938f;
            --aero-accent: #67d9cb;
            --aero-accent-soft: #8ce1c0;
            --aero-warn: #e7b36f;
            --aero-danger: #ed8d80;
            --aero-surface: rgba(15, 25, 30, 0.96);
        }

        html, body, [data-testid="stAppViewContainer"] {
            background: var(--aero-bg);
            color: var(--aero-text);
            font-family: "Bahnschrift", "Aptos", "Segoe UI", sans-serif;
        }

        .stApp {
            background-color: var(--aero-bg);
            background-image: linear-gradient(180deg, rgba(30, 57, 58, 0.16), transparent 260px),
                              repeating-linear-gradient(0deg, transparent 0 39px, rgba(177, 208, 204, 0.018) 40px),
                              linear-gradient(180deg, #0b151a 0%, #091116 100%);
            color: var(--aero-text);
        }

        [data-testid="stHeader"] {
            background: rgba(7, 18, 25, 0.84);
            border-bottom: 1px solid var(--aero-border);
            backdrop-filter: blur(8px);
        }

        [data-testid="stToolbar"] {
            display: none;
        }

        [data-testid="stSidebar"] {
            background: rgba(11, 19, 23, 0.98);
            border-right: 1px solid var(--aero-border);
            width: 250px !important;
        }

        [data-testid="stSidebarContent"] {
            padding: 0.8rem 0.7rem 1rem;
        }

        [data-testid="stMainBlockContainer"] {
            padding: 0.55rem 1.25rem 1.2rem;
            max-width: 1900px;
        }

        .block-container {
            padding-top: 0.15rem !important;
            padding-bottom: 0.2rem !important;
        }

        .aerosphere-shell {
            min-height: calc(100vh - 110px);
        }

        .aerosphere-brand {
            display: flex;
            align-items: center;
            gap: 0.65rem;
            font-size: 0.9rem;
            font-weight: 700;
            letter-spacing: 0.22em;
            text-transform: uppercase;
            color: var(--aero-text);
            padding: 0.2rem 0.4rem 0.5rem;
        }

        .aerosphere-mark {
            width: 1.65rem;
            height: 1.65rem;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: rgba(106, 199, 216, 0.08);
            border: 1px solid var(--aero-border-strong);
            color: var(--aero-accent);
            font-size: 0.7rem;
        }

        .workspace-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            padding: 0.25rem 0 0.55rem;
            border-bottom: 1px solid var(--aero-border);
            margin-bottom: 0.5rem;
            min-height: 3.2rem;
        }

        .workspace-header-left {
            display: flex;
            align-items: center;
            gap: 0.9rem;
            min-width: 0;
            flex: 1 1 auto;
        }

        .workspace-header-title {
            margin: 0;
            font-size: 1.65rem;
            letter-spacing: 0;
            line-height: 1.1;
            font-weight: 700;
            color: var(--aero-text);
        }

        .eyebrow {
            font-size: 0.62rem;
            letter-spacing: 0.22em;
            text-transform: uppercase;
            color: var(--aero-accent);
            margin: 0 0 0.18rem 0;
            font-weight: 700;
        }

        .workspace-header-right {
            display: flex;
            align-items: center;
            gap: 0.7rem;
            flex-shrink: 0;
        }

        .workspace-status {
            display: inline-flex;
            align-items: center;
            gap: 0.55rem;
            padding: 0.5rem 0.7rem;
            border-radius: 4px;
            border: 1px solid var(--aero-border-strong);
            background: rgba(11, 25, 31, 0.8);
            color: var(--aero-text-soft);
            font-size: 0.62rem;
            letter-spacing: 0.18em;
            text-transform: uppercase;
        }

        .status-dot {
            width: 0.45rem;
            height: 0.45rem;
            border-radius: 50%;
            background: var(--aero-accent-soft);
            box-shadow: 0 0 0.5rem rgba(86, 224, 196, 0.8);
        }

        .workspace-panel {
            background: rgba(15, 25, 30, 0.9);
            border: 1px solid var(--aero-border);
            border-radius: 6px;
            padding: 0.9rem 0.95rem;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
        }

        .workspace-panel h3,
        .workspace-panel h4,
        .workspace-panel h5,
        .workspace-panel h6 {
            margin-top: 0;
            color: var(--aero-text);
        }

        .context-panel {
            background: rgba(15, 24, 29, 0.82);
            border: 1px solid var(--aero-border);
            border-radius: 6px;
            padding: 0.8rem 0.85rem;
        }

        .context-panel .small-label {
            font-size: 0.62rem;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: var(--aero-accent);
            margin-bottom: 0.5rem;
        }

        .status-strip {
            margin-top: 0.8rem;
            padding-top: 0.7rem;
            border-top: 1px solid var(--aero-border);
            display: flex;
            gap: 0.55rem;
            flex-wrap: wrap;
        }

        .status-item {
            min-width: 122px;
            border: 1px solid var(--aero-border);
            background: rgba(9, 18, 24, 0.8);
            border-radius: 0.5rem;
            padding: 0.45rem 0.6rem;
        }

        .status-item .key {
            font-size: 0.58rem;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: var(--aero-text-muted);
        }

        .status-item .value {
            margin-top: 0.18rem;
            font-size: 0.8rem;
            font-weight: 700;
            color: var(--aero-text);
        }

        .metric-value {
            font-size: 1.1rem;
            font-weight: 700;
            letter-spacing: 0;
            color: var(--aero-text);
        }

        .nav-shell {
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
            margin-top: 0.4rem;
        }

        .nav-item {
            width: 100%;
            padding: 0.7rem 0.7rem;
            border-radius: 0.65rem;
            border: 1px solid transparent;
            background: transparent;
            color: var(--aero-text-soft);
            font-size: 0.7rem;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            text-align: left;
            transition: all 0.15s ease;
        }

        .nav-item.active {
            background: rgba(106, 199, 216, 0.09);
            border-color: var(--aero-border-strong);
            color: var(--aero-text);
            box-shadow: inset 0 0 0 1px rgba(106, 199, 216, 0.08);
        }

        .nav-item:hover {
            background: rgba(125, 147, 167, 0.06);
            border-color: var(--aero-border);
            color: var(--aero-text);
        }

        .stButton > button {
            border-radius: 4px;
            border: 1px solid var(--aero-border-strong);
            background: rgba(20, 34, 39, 0.88);
            color: var(--aero-text);
            padding: 0.52rem 0.8rem;
            font-weight: 600;
            transition: background 0.15s ease, border-color 0.15s ease;
        }

        .stButton > button:hover {
            border-color: var(--aero-accent);
            color: var(--aero-text);
        }

        .stButton > button[kind="primary"] {
            background: linear-gradient(180deg, rgba(63, 160, 145, 0.28), rgba(47, 116, 109, 0.2));
            border-color: rgba(106, 199, 216, 0.5);
            color: var(--aero-text);
        }

        [data-testid="stMetric"] {
            background: rgba(16, 27, 32, 0.72);
            border: 1px solid var(--aero-border);
            border-radius: 5px;
            padding: 0.7rem 0.8rem;
        }

        [data-testid="stMetricLabel"] p {
            color: var(--aero-text-muted);
            font-size: 0.72rem;
        }

        [data-testid="stMetricValue"] {
            color: var(--aero-text);
            font-size: 1.35rem;
        }

        [data-testid="stExpander"] {
            border-color: var(--aero-border);
            border-radius: 5px;
            background: rgba(14, 24, 29, 0.55);
        }

        [data-testid="stSidebarNav"] {
            padding-top: 0.3rem;
        }

        [data-testid="stSidebarNav"] li > a {
            border: 1px solid transparent;
            border-radius: 0.6rem;
            padding: 0.55rem 0.7rem;
            color: var(--aero-text-soft);
            background: transparent;
            font-size: 0.7rem;
            letter-spacing: 0.14em;
            text-transform: uppercase;
        }

        [data-testid="stSidebarNav"] li > a:hover {
            background: rgba(106, 199, 216, 0.06);
            border-color: var(--aero-border);
            color: var(--aero-text);
        }

        [data-testid="stSidebarNav"] li > a[aria-current="page"] {
            background: rgba(106, 199, 216, 0.09);
            border-color: var(--aero-border-strong);
            color: var(--aero-text);
        }

        .small-muted {
            color: var(--aero-text-muted);
            font-size: 0.72rem;
        }

        .thin-divider {
            border-top: 1px solid var(--aero-border);
            margin-top: 0.7rem;
            padding-top: 0.7rem;
        }

        .mission-summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 0.7rem;
            margin-top: 0.8rem;
        }

        .summary-card {
            border: 1px solid var(--aero-border);
            background: rgba(16, 27, 32, 0.88);
            border-radius: 5px;
            padding: 0.75rem 0.8rem;
            min-height: 5.3rem;
        }

        .summary-card .label {
            display: block;
            font-size: 0.58rem;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: var(--aero-text-muted);
            margin-bottom: 0.35rem;
        }

        .summary-card .value {
            font-size: 1.2rem;
            font-weight: 700;
            letter-spacing: 0;
            color: var(--aero-text);
            overflow-wrap: anywhere;
        }

        .pipeline-rail {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 0.55rem;
            margin-top: 0.9rem;
        }

        .pipeline-step {
            border: 1px solid var(--aero-border);
            background: rgba(16, 27, 32, 0.88);
            border-radius: 5px;
            padding: 0.6rem 0.65rem;
            min-height: 110px;
            height: 100%;
        }

        .pipeline-step .step-number {
            font-size: 0.56rem;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: var(--aero-text-muted);
        }

        .pipeline-step .step-name {
            margin-top: 0.35rem;
            font-size: 0.8rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }

        .pipeline-step .step-meta {
            margin-top: 0.2rem;
            font-size: 0.68rem;
            color: var(--aero-text-soft);
            line-height: 1.45;
        }

        .pipeline-step .step-description {
            margin-top: 0.45rem;
            color: var(--aero-text-muted);
            font-size: 0.75rem;
            line-height: 1.5;
        }

        .pipeline-step .stage-state {
            display: inline-block;
            margin-top: 0.45rem;
            padding: 0.18rem 0.38rem;
            border: 1px solid var(--aero-border-strong);
            border-radius: 3px;
            color: var(--aero-accent);
            font-size: 0.58rem;
            font-weight: 700;
            letter-spacing: 0.1em;
        }

        .pipeline-step[data-state="PENDING"] .stage-state,
        .pipeline-step[data-state="BLOCKED"] .stage-state {
            border-color: var(--aero-border);
            color: var(--aero-text-muted);
        }

        .pipeline-step[data-state="FAILED"] .stage-state {
            border-color: rgba(237, 141, 128, 0.5);
            color: var(--aero-danger);
        }

        .world-hero {
            border: 1px solid var(--aero-border);
            border-radius: 6px;
            background: rgba(7, 14, 19, 0.8);
            overflow: hidden;
            min-height: 790px;
        }

        .world-hero .stPlotlyChart {
            background: transparent;
        }

        .compact-label {
            font-size: 0.62rem;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: var(--aero-text-muted);
        }

        @media (max-width: 800px) {
            [data-testid="stMainBlockContainer"] {
                padding: 0.45rem 0.75rem 1rem;
            }

            .workspace-header {
                align-items: flex-start;
                flex-direction: column;
                gap: 0.6rem;
            }

            .workspace-header-left {
                flex-wrap: wrap;
            }

            .workspace-header-title {
                font-size: 1.35rem;
                overflow-wrap: anywhere;
            }

            .world-hero {
                min-height: 0;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_strip(stats):
    items = []
    for key, value in stats.items():
        items.append(f'<div class="status-item"><div class="key">{key}</div><div class="value">{value}</div></div>')
    st.markdown(f'<div class="status-strip">{"".join(items)}</div>', unsafe_allow_html=True)


def workspace_header(title, mission_name, status_label='READY', actions=None):
    st.markdown(
        f'''<div class="workspace-header">
            <div class="workspace-header-left">
                <div class="aerosphere-brand"><span class="aerosphere-mark">◈</span> AeroSphere</div>
                <div>
                    <div class="eyebrow">Single-pass spatial intelligence</div>
                    <div class="workspace-header-title">{mission_name}</div>
                </div>
            </div>
            <div class="workspace-header-right">
                <div class="workspace-status"><span class="status-dot"></span>{status_label}</div>
            </div>
        </div>''',
        unsafe_allow_html=True,
    )
    if actions:
        action_row = st.columns(len(actions))
        for idx, action in enumerate(actions):
            with action_row[idx]:
                if action.get('type') == 'button':
                    st.button(action['label'], key=action.get('key', action['label']), on_click=action.get('on_click'), args=action.get('args', ()))
                elif action.get('type') == 'link':
                    st.link_button(action['label'], action['url'])
