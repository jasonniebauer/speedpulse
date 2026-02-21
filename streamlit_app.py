# Standard Python Libraries
import time
import threading
from collections import deque
from datetime import datetime

# User Interface
import streamlit as st

# Data Handling & Visualization
import pandas as pd
from streamlit_echarts import st_echarts

# Measuring Internet Bandwidth
import speedtest


# ────────────────────────────────────────────────
#   Config
# ────────────────────────────────────────────────

INTERVAL_SEC = 30
REFRESH_SEC  = 1

# ────────────────────────────────────────────────
#   Shared state via st.cache_resource
# ────────────────────────────────────────────────

@st.cache_resource
def get_shared_state():
    return {
        "history":        deque(maxlen=120),
        "thread_started": False,
        "lock":           threading.Lock(),
        "last_test_time": None,
        "testing":        False,
    }

state = get_shared_state()

# ────────────────────────────────────────────────
#   Background thread
# ────────────────────────────────────────────────

def speedtest_worker():
    while True:
        state["testing"] = True
        try:
            s = speedtest.Speedtest(secure=True)
            s.get_best_server()
            down = s.download() / 1_000_000
            up   = s.upload()   / 1_000_000
            ping = s.results.ping
            now  = datetime.now()

            state["history"].append({
                "time":     now.strftime("%I:%M:%S %p"),
                "datetime": now,
                "download": round(down, 2),
                "upload":   round(up, 2),
                "ping":     round(ping, 1),
                "error":    None,
            })
            state["last_test_time"] = now

        except Exception as e:
            now = datetime.now()
            state["history"].append({
                "time":     now.strftime("%I:%M:%S %p"),
                "datetime": now,
                "download": None,
                "upload":   None,
                "ping":     None,
                "error":    str(e)[:100],
            })
            state["last_test_time"] = now

        finally:
            state["testing"] = False

        time.sleep(INTERVAL_SEC)

with state["lock"]:
    if not state["thread_started"]:
        t = threading.Thread(target=speedtest_worker, daemon=True)
        t.start()
        state["thread_started"] = True

# ────────────────────────────────────────────────
#   ECharts helpers
# ────────────────────────────────────────────────

def make_line_chart(times, values, title, color, y_unit):
    return {
        "title":   {"text": title, "textStyle": {"fontSize": 14}},
        "tooltip": {
            "trigger": "axis",
            "formatter": f"{{b}}<br/>{{a}}: {{c}} {y_unit}",
        },
        "grid":    {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
        "xAxis":   {
            "type": "category",
            "data": times,
            "axisLabel": {"rotate": 30, "fontSize": 10},
            "boundaryGap": False,
        },
        "yAxis":   {
            "type":      "value",
            "axisLabel": {"formatter": f"{{value}} {y_unit}"},
        },
        "series": [{
            "name":       title,
            "type":       "line",
            "data":       values,
            "smooth":     False,
            "symbol":     "circle",
            "symbolSize": 6,
            "lineStyle":  {"color": color, "width": 2},
            "itemStyle":  {"color": color},
            "areaStyle":  {
                "color": {
                    "type":       "linear",
                    "x": 0, "y": 0, "x2": 0, "y2": 1,
                    "colorStops": [
                        {"offset": 0, "color": color + "55"},
                        {"offset": 1, "color": color + "00"},
                    ],
                }
            },
        }],
    }

# ────────────────────────────────────────────────
#   UI
# ────────────────────────────────────────────────

st.title("SpeedPulse")

@st.fragment(run_every=REFRESH_SEC)
def dashboard():
    history_snapshot = list(state["history"])
    last_test        = state["last_test_time"]
    is_testing       = state["testing"]

    # ── Status bar ──
    if is_testing:
        st.caption("🔄 Running speed test…")
    elif last_test is None:
        st.caption("⏳ Waiting for first speed test…")
    else:
        elapsed     = int((datetime.now() - last_test).total_seconds())
        next_in     = max(0, INTERVAL_SEC - elapsed)
        mins, secs  = divmod(elapsed, 60)
        elapsed_str = f"{mins}m {secs}s ago" if mins else f"{secs}s ago"
        st.caption(
            f"✅ Last test: **{last_test.strftime('%I:%M:%S %p')}** ({elapsed_str}) • "
            f"Next test in **{next_in}s** • "
            f"Powered by speedtest.net"
        )

    if not history_snapshot:
        st.info("⏳ Running first speed test… this usually takes 10–30 seconds.")
        return

    df = pd.DataFrame(history_snapshot)

    errors = df[df["error"].notna()]
    if not errors.empty:
        st.warning(f"⚠️ {len(errors)} test(s) failed. Latest: {errors.iloc[-1]['error']}")

    df_clean = df[df["download"].notna()]

    if df_clean.empty:
        st.error("All speed tests have failed. Check your internet connection.")
        return

    # ── Latest readings ──
    latest = df_clean.iloc[-1]
    c1, c2, c3 = st.columns(3)
    c1.metric("⬇️ Download", f"{latest['download']} Mbps")
    c2.metric("⬆️ Upload",   f"{latest['upload']} Mbps")
    c3.metric("🏓 Ping",     f"{latest['ping']} ms")

    times         = df_clean["time"].tolist()
    download_vals = df_clean["download"].tolist()
    upload_vals   = df_clean["upload"].tolist()
    ping_vals     = df_clean["ping"].tolist()

    # ── ECharts line charts ──
    col1, col2 = st.columns(2)
    with col1:
        st_echarts(
            options=make_line_chart(times, download_vals, "Download Speed", "#00CC96", "Mbps"),
            height="300px",
        )
    with col2:
        st_echarts(
            options=make_line_chart(times, upload_vals, "Upload Speed", "#FFA15A", "Mbps"),
            height="300px",
        )

    st_echarts(
        options=make_line_chart(times, ping_vals, "Ping", "#E74C3C", "ms"),
        height="300px",
    )

    st.dataframe(
        df_clean.tail(15)[["time", "download", "upload", "ping"]]
            .rename(columns={
                "time":     "Time",
                "download": "Download (Mbps)",
                "upload":   "Upload (Mbps)",
                "ping":     "Ping (ms)",
            })
            .iloc[::-1]
            .reset_index(drop=True),
        use_container_width=True,
        hide_index=True
    )

dashboard()