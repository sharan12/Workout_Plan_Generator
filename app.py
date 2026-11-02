import datetime
import json
import os
import time
from typing import Any, Dict, List, Optional
import requests
import streamlit as st
from dotenv import load_dotenv

# Load local environment
load_dotenv(override=True)

# Import local backend functions for graceful standalone fallback
try:
    from api import generate_workout_plan as direct_generate_plan
    from api import swap_workout_exercise as direct_swap_exercise
    LOCAL_API_IMPORT_AVAILABLE = True
except Exception:
    LOCAL_API_IMPORT_AVAILABLE = False


# ==========================================
# Page Configuration & Modern Theme Styling
# ==========================================

st.set_page_config(
    page_title="IronPulse - AI Workout Plan Generator",
    page_icon="🏋️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for high-impact visual design
st.markdown(
    """
    <style>
    /* Global Styles & Font adjustments */
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Hero Banner */
    .hero-container {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #042f2e 100%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 18px;
        padding: 2.2rem 2.5rem;
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
    }
    .hero-title {
        font-size: 2.5rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        background: linear-gradient(90deg, #38bdf8 0%, #34d399 50%, #a78bfa 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.4rem;
    }
    .hero-subtitle {
        color: #94a3b8;
        font-size: 1.1rem;
        font-weight: 400;
        margin-bottom: 0;
        max-width: 800px;
        line-height: 1.5;
    }
    .badge-pill {
        display: inline-block;
        font-size: 0.75rem;
        font-weight: 600;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        background: rgba(56, 189, 248, 0.15);
        color: #38bdf8;
        border: 1px solid rgba(56, 189, 248, 0.3);
        margin-bottom: 0.75rem;
    }

    /* Card styling */
    .glass-card {
        background: rgba(30, 41, 59, 0.5);
        border: 1px solid rgba(148, 163, 184, 0.12);
        border-radius: 14px;
        padding: 1.25rem;
        margin-bottom: 1rem;
    }

    /* Status indicator */
    .status-badge-online {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        background: rgba(34, 197, 94, 0.15);
        border: 1px solid rgba(34, 197, 94, 0.3);
        color: #4ade80;
        border-radius: 8px;
        font-size: 0.82rem;
        font-weight: 600;
    }
    .status-badge-offline {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        background: rgba(234, 179, 8, 0.15);
        border: 1px solid rgba(234, 179, 8, 0.3);
        color: #facc15;
        border-radius: 8px;
        font-size: 0.82rem;
        font-weight: 600;
    }

    /* Tables */
    div[data-testid="stMarkdownContainer"] table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid rgba(148, 163, 184, 0.2);
        margin: 1.2rem 0;
    }
    div[data-testid="stMarkdownContainer"] th {
        background-color: rgba(30, 41, 59, 0.8);
        color: #38bdf8;
        font-weight: 700;
        padding: 10px 14px;
        text-align: left;
        border-bottom: 2px solid rgba(56, 189, 248, 0.3);
    }
    div[data-testid="stMarkdownContainer"] td {
        padding: 10px 14px;
        border-bottom: 1px solid rgba(148, 163, 184, 0.1);
        color: #e2e8f0;
    }
    div[data-testid="stMarkdownContainer"] tr:hover td {
        background-color: rgba(56, 189, 248, 0.05);
    }

    /* Disclaimer box */
    .disclaimer-box {
        background: rgba(239, 68, 68, 0.1);
        border-left: 4px solid #ef4444;
        border-radius: 0 10px 10px 0;
        padding: 1rem 1.2rem;
        margin-top: 1.5rem;
        color: #fca5a5;
        font-size: 0.9rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==========================================
# Session State Initialization
# ==========================================

if "workout_plan" not in st.session_state:
    st.session_state.workout_plan = None
if "last_inputs" not in st.session_state:
    st.session_state.last_inputs = {}
if "swap_history" not in st.session_state:
    st.session_state.swap_history = []
if "generation_count" not in st.session_state:
    st.session_state.generation_count = 0


# ==========================================
# Backend API Communication Helper
# ==========================================

def check_backend_health(base_url: str) -> Dict[str, Any]:
    """Test connection to the FastAPI backend."""
    try:
        resp = requests.get(f"{base_url.rstrip('/')}/health", timeout=2.0)
        if resp.status_code == 200:
            return {"online": True, "data": resp.json()}
    except Exception:
        pass
    return {"online": False, "data": {}}


def call_generate_plan_api(
    base_url: str,
    payload: dict,
    api_key_override: Optional[str] = None,
    model_override: Optional[str] = None,
    use_direct_fallback: bool = True,
) -> Dict[str, Any]:
    """
    Call the FastAPI /generate-plan endpoint, falling back to local Python function
    if FastAPI is not running or direct mode is preferred.
    """
    # 1. Try FastAPI endpoint first
    try:
        url = f"{base_url.rstrip('/')}/generate-plan"
        resp = requests.post(url, json=payload, timeout=60.0)
        if resp.status_code == 200:
            return {"success": True, "source": "FastAPI Service", "data": resp.json()}
        else:
            try:
                error_detail = resp.json().get("detail", resp.text)
            except Exception:
                error_detail = resp.text
            return {"success": False, "source": "FastAPI Service", "error": f"API Error ({resp.status_code}): {error_detail}"}
    except requests.exceptions.ConnectionError:
        # FastAPI backend is not running
        if use_direct_fallback and LOCAL_API_IMPORT_AVAILABLE:
            try:
                # Call local generator function directly
                plan = direct_generate_plan(
                    fitness_goal=payload["fitness_goal"],
                    experience_level=payload["experience_level"],
                    days_per_week=payload["days_per_week"],
                    equipment_access=payload["equipment_access"],
                    injuries_limitations=payload.get("injuries_limitations"),
                    session_duration_minutes=payload.get("session_duration_minutes", 45),
                    variation_seed=payload.get("variation_seed"),
                    api_key=api_key_override,
                    model=model_override,
                )
                return {
                    "success": True,
                    "source": "Direct Groq Engine (Standalone)",
                    "data": {
                        "plan_markdown": plan,
                        "model_used": model_override or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
                        "injuries_noted": bool(payload.get("injuries_limitations")),
                    },
                }
            except Exception as e:
                return {"success": False, "source": "Direct Groq Engine", "error": str(e)}
        else:
            return {
                "success": False,
                "source": "Connection Error",
                "error": f"Could not connect to FastAPI at {base_url}. Ensure 'uv run uvicorn api:app --reload' is running.",
            }
    except Exception as e:
        return {"success": False, "source": "Client Error", "error": str(e)}


def call_swap_exercise_api(
    base_url: str,
    payload: dict,
    api_key_override: Optional[str] = None,
    model_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Call exercise substitution endpoint or local fallback."""
    try:
        url = f"{base_url.rstrip('/')}/swap-exercise"
        resp = requests.post(url, json=payload, timeout=30.0)
        if resp.status_code == 200:
            return {"success": True, "data": resp.json()}
        else:
            return {"success": False, "error": resp.json().get("detail", resp.text)}
    except requests.exceptions.ConnectionError:
        if LOCAL_API_IMPORT_AVAILABLE:
            try:
                res = direct_swap_exercise(
                    exercise_to_swap=payload["exercise_to_swap"],
                    reason=payload["reason"],
                    equipment_access=payload["equipment_access"],
                    injuries_limitations=payload.get("injuries_limitations"),
                    api_key=api_key_override,
                    model=model_override,
                )
                return {"success": True, "data": {"swap_suggestions_markdown": res}}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": f"FastAPI backend unreachable at {base_url}."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==========================================
# Sidebar Configuration & Backend Monitor
# ==========================================

with st.sidebar:
    st.markdown("### ⚙️ System & Model Config")

    backend_url = st.text_input(
        "FastAPI Service URL",
        value=os.getenv("FASTAPI_URL", "http://127.0.0.1:8000"),
        help="Address of the FastAPI backend service (api.py).",
    )

    # Ping health check
    health = check_backend_health(backend_url)
    if health["online"]:
        st.markdown(
            '<div class="status-badge-online">● FastAPI Backend Online</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="status-badge-offline">▲ Backend Offline (Direct Mode Active)</div>',
            unsafe_allow_html=True,
        )
        st.caption("FastAPI is not detected at this URL. Don't worry! Direct Groq mode is active, or run: `uv run uvicorn api:app --reload`")

    st.divider()

    st.markdown("#### 🤖 LLM Model Selection")
    model_options = [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "qwen/qwen3.8-27b",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
    ]
    current_env_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    default_idx = model_options.index(current_env_model) if current_env_model in model_options else 0

    selected_model = st.selectbox(
        "Groq Model",
        options=model_options,
        index=default_idx,
        help="Select the LLM model to power your workout routine generation.",
    )

    # Optional API key override
    env_has_key = bool(os.getenv("GROQ_API_KEY") and os.getenv("GROQ_API_KEY") not in ("<api-key>", "your_groq_api_key_here"))
    api_key_override = st.text_input(
        "Groq API Key (Override)",
        type="password",
        value="",
        placeholder="Key loaded from .env" if env_has_key else "gsk_...",
        help="Leave blank to use the GROQ_API_KEY from your .env file.",
    )

    if env_has_key:
        st.success("✅ `.env` API Key Detected")
    elif not api_key_override:
        st.warning("⚠️ No GROQ_API_KEY detected in .env. Enter one above.")

    st.divider()

    st.markdown("#### 📊 Current Session")
    st.metric("Plans Generated", st.session_state.generation_count)
    if st.session_state.workout_plan:
        st.caption(f"Last updated: {datetime.datetime.now().strftime('%H:%M:%S')}")
        if st.button("🗑️ Clear Current Plan", use_container_width=True):
            st.session_state.workout_plan = None
            st.session_state.last_inputs = {}
            st.session_state.swap_history = []
            st.rerun()

    st.markdown("---")
    st.markdown(
        """
        <div style="font-size: 0.78rem; color: #64748b; line-height: 1.4;">
        <b>Architecture:</b><br>
        • Backend: <code>api.py</code> (FastAPI)<br>
        • Frontend: <code>app.py</code> (Streamlit)<br>
        • Engine: Groq High-Speed LLM Inference
        </div>
        """,
        unsafe_allow_html=True,
    )


# ==========================================
# Main App Header / Hero Banner
# ==========================================

st.markdown(
    """
    <div class="hero-container">
        <span class="badge-pill">⚡ Created by Sharan</span>
        <h1 class="hero-title">IronPulse Workout Generator</h1>
        <p class="hero-subtitle">
            An intelligent strength & conditioning assistant that constructs biomechanically sound, 
            constraint-honoring weekly workout routines. Every exercise respects your equipment, time, and physical limitations.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ==========================================
# Structured Inputs Section (2 Columns)
# ==========================================

st.subheader("📋 Step 1: Tell Us About Your Profile & Goals")

col_left, col_right = st.columns([1, 1], gap="large")

with col_left:
    st.markdown("##### 🎯 Training Objectives & Schedule")

    fitness_goal = st.selectbox(
        "What is your primary fitness goal?",
        options=[
            "Build muscle",
            "Lose fat",
            "General fitness",
            "Improve endurance",
        ],
        index=0,
        help="This guides the rep ranges, intensity, and progressive overload protocols.",
    )

    experience_level = st.selectbox(
        "What is your training experience level?",
        options=[
            "Beginner",
            "Intermediate",
            "Advanced",
        ],
        index=1,
        help="Beginners receive simpler compound movement learning; advanced users receive periodized volume.",
    )

    days_per_week = st.slider(
        "Days available per week for workouts",
        min_value=1,
        max_value=7,
        value=4,
        help="Choose between 1 and 7 days. The plan will create an exact schedule for this count.",
    )

    # Visual split recommendation helper
    split_recommendations = {
        1: "Single Full Body session (Comprehensive full-body stimulus)",
        2: "2-Day Split: Full Body A & Full Body B",
        3: "3-Day Split: Full Body rotations or Push / Pull / Legs",
        4: "4-Day Split: Upper / Lower or Torso / Limbs (Ideal for hypertrophy)",
        5: "5-Day Split: Upper / Lower + Push / Pull / Legs",
        6: "6-Day Split: Push / Pull / Legs (PPL) x2 (High volume)",
        7: "7-Day Split: Rotational split with dedicated active recovery & mobility",
    }
    st.caption(f"💡 Recommended split: *{split_recommendations.get(days_per_week)}*")

with col_right:
    st.markdown("##### 🏋️ Equipment Access & Physical Constraints")

    equipment_options = [
        "Full gym",
        "Home dumbbells",
        "No equipment",
        "Resistance bands",
        "Pull-up bar",
        "Kettlebells",
    ]

    selected_equipment = st.multiselect(
        "What equipment do you have access to?",
        options=equipment_options,
        default=["Home dumbbells", "Pull-up bar"],
        help="Crucial constraint: the generator strictly limits prescribed exercises to this equipment list.",
    )

    session_duration = st.select_slider(
        "Target workout duration per session (minutes)",
        options=[20, 30, 45, 60, 75, 90],
        value=45,
        help="Helps the coach calibrate exercise count, supersets, and rest times.",
    )

    injuries_limitations = st.text_input(
        "Injuries, joint pain, or movement limitations (Optional)",
        value="",
        placeholder="e.g. 'bad knees, avoid deep squats', 'rotator cuff discomfort', 'lower back strain'",
        help="The coach will strictly eliminate aggravating movements and substitute joint-safe alternatives.",
    )

    # Quick suggestion chips
    st.caption("Quick examples:")
    chip_cols = st.columns(4)
    if chip_cols[0].button("Bad knees", key="chip_knees"):
        injuries_limitations = "Bad knees, avoid deep squats and heavy lunges"
        st.rerun()
    if chip_cols[1].button("Lower back", key="chip_back"):
        injuries_limitations = "Lower back sensitivity, avoid heavy spinal loading"
        st.rerun()
    if chip_cols[2].button("Shoulder pain", key="chip_shoulder"):
        injuries_limitations = "Shoulder pain, no heavy overhead pressing"
        st.rerun()
    if chip_cols[3].button("Clear / None", key="chip_clear"):
        injuries_limitations = ""
        st.rerun()


# ==========================================
# Action Buttons & Execution
# ==========================================

st.markdown("<br>", unsafe_allow_html=True)
btn_col1, btn_col2, btn_col3 = st.columns([1.5, 1.5, 2.5])

generate_clicked = btn_col1.button("🚀 Generate Workout Plan", type="primary", use_container_width=True)
regenerate_clicked = btn_col2.button("🔄 Regenerate Variation", disabled=(st.session_state.workout_plan is None), use_container_width=True)

# Build current payload
active_equipment = selected_equipment if selected_equipment else ["No equipment"]
current_payload = {
    "fitness_goal": fitness_goal,
    "experience_level": experience_level,
    "days_per_week": int(days_per_week),
    "equipment_access": active_equipment,
    "injuries_limitations": injuries_limitations.strip() if injuries_limitations else None,
    "session_duration_minutes": int(session_duration),
}

# Handle Generation
if generate_clicked or regenerate_clicked:
    # 1. Basic validation
    if days_per_week <= 0 or days_per_week > 7:
        st.error("❌ Days available per week must be between 1 and 7.")
    elif not selected_equipment:
        st.warning("⚠️ No equipment selected. Defaulting to 'No equipment (Bodyweight)'calisthenics routine.")
        current_payload["equipment_access"] = ["No equipment"]

    if regenerate_clicked:
        current_payload["variation_seed"] = f"variation_{int(time.time())}"

    # Call LLM backend
    with st.spinner("🧠 Analyzing parameters, biomechanics & programming optimal routine via Groq..."):
        result = call_generate_plan_api(
            base_url=backend_url,
            payload=current_payload,
            api_key_override=api_key_override if api_key_override else None,
            model_override=selected_model,
        )

    if result.get("success"):
        st.session_state.workout_plan = result["data"]["plan_markdown"]
        st.session_state.last_inputs = current_payload
        st.session_state.last_source = result.get("source", "FastAPI Service")
        st.session_state.generation_count += 1
        st.toast("✅ Personalized workout routine generated successfully!", icon="🎉")
    else:
        st.error(f"❌ Failed to generate workout plan: {result.get('error')}")
        st.info("Tip: Verify your GROQ_API_KEY in `.env` or in the sidebar, and ensure your model selection is valid.")


# ==========================================
# Plan Display & Interactive Tools
# ==========================================

if st.session_state.workout_plan:
    st.markdown("---")
    st.subheader("🏋️ Your Personalized Weekly Training Program")

    # Metrics summary header
    inputs = st.session_state.last_inputs
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Goal", inputs.get("fitness_goal", fitness_goal))
    m2.metric("Level", inputs.get("experience_level", experience_level))
    m3.metric("Frequency", f"{inputs.get('days_per_week', days_per_week)} Days / Wk")
    m4.metric("Session Length", f"{inputs.get('session_duration_minutes', session_duration)} Mins")
    equip_display = ", ".join(inputs.get("equipment_access", []))
    if len(equip_display) > 22:
        equip_display = equip_display[:20] + "..."
    m5.metric("Equipment", equip_display)

    if inputs.get("injuries_limitations"):
        st.info(f"🩹 **Injury Safeguards Active:** Custom modifications applied for: *{inputs.get('injuries_limitations')}*")

    # Tab navigation for Full Plan, Exercise Swap Assistant, and Export
    tab_plan, tab_swap, tab_export = st.tabs([
        "📖 Complete Weekly Schedule",
        "🔄 Exercise Swap Assistant (Mini-Feature)",
        "💾 Export & Download Plan",
    ])

    with tab_plan:
        st.markdown(st.session_state.workout_plan, unsafe_allow_html=True)

    with tab_swap:
        st.markdown(
            """
            #### 🔄 Need to Swap an Exercise?
            If an exercise in your plan feels uncomfortable, aggravates a joint, or you don't have the exact equipment,
            enter it below to get 3 biomechanically matched alternative exercises.
            """
        )

        sc1, sc2 = st.columns([1, 1])
        with sc1:
            exercise_to_swap = st.text_input(
                "Exercise name to replace",
                placeholder="e.g. Barbell Back Squat, Dumbbell Shoulder Press, Pull-ups",
            )
            swap_reason = st.selectbox(
                "Reason for replacement",
                options=[
                    "Joint discomfort / Pain",
                    "Missing equipment / Machine occupied",
                    "Movement too challenging (need regression)",
                    "Want more variety / Bored of this movement",
                ],
            )
        with sc2:
            st.markdown("<br>", unsafe_allow_html=True)
            find_swap_btn = st.button("🔍 Find Alternative Exercises", type="primary", use_container_width=True)

        if find_swap_btn:
            if not exercise_to_swap.strip():
                st.warning("Please specify an exercise name to swap.")
            else:
                swap_payload = {
                    "exercise_to_swap": exercise_to_swap.strip(),
                    "reason": swap_reason,
                    "equipment_access": inputs.get("equipment_access", active_equipment),
                    "injuries_limitations": inputs.get("injuries_limitations"),
                }
                with st.spinner("Finding biomechanically sound exercise substitutes..."):
                    swap_res = call_swap_exercise_api(
                        base_url=backend_url,
                        payload=swap_payload,
                        api_key_override=api_key_override if api_key_override else None,
                        model_override=selected_model,
                    )
                if swap_res.get("success"):
                    suggestions = swap_res["data"]["swap_suggestions_markdown"]
                    st.session_state.swap_history.append({
                        "original": exercise_to_swap,
                        "reason": swap_reason,
                        "alternatives": suggestions,
                    })
                    st.markdown("### 💡 Recommended Substitutes:")
                    st.markdown(suggestions)
                else:
                    st.error(f"Error finding substitutes: {swap_res.get('error')}")

        if st.session_state.swap_history:
            with st.expander("🕒 Previous Exercise Swaps this session"):
                for item in reversed(st.session_state.swap_history):
                    st.markdown(f"**Replaced:** `{item['original']}` (Reason: *{item['reason']}*)")
                    st.markdown(item["alternatives"])
                    st.divider()

    with tab_export:
        st.markdown("#### 💾 Save Your Routine")
        st.write("Download your custom workout program to keep on your phone or print for your gym notebook.")

        plan_content = st.session_state.workout_plan
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        goal_filename = inputs.get("fitness_goal", "workout").lower().replace(" ", "_")

        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                label="📥 Download as Markdown (.md)",
                data=plan_content,
                file_name=f"ironpulse_{goal_filename}_{timestamp_str}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with col_dl2:
            st.download_button(
                label="📄 Download as Plain Text (.txt)",
                data=plan_content,
                file_name=f"ironpulse_{goal_filename}_{timestamp_str}.txt",
                mime="text/plain",
                use_container_width=True,
            )

        st.caption("Tip: You can also copy/paste directly from the Complete Weekly Schedule tab!")

else:
    # Helpful empty state
    st.info("👋 Fill in your parameters above and click **'🚀 Generate Workout Plan'** to construct your custom training program.")
