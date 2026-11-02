# 🏋️ IronPulse - AI Workout Plan Generator

A full-stack fitness programming application built with **FastAPI**, **Streamlit**, and the **Groq LLM API**. It collects structured inputs about a user's fitness goals, schedule, equipment, and injuries, and generates a personalized, safe, weekly workout routine.

> **Created by Sharan**

---

## 📁 Project Architecture & Two-File Setup

Per the assignment specifications, the application is divided into two distinct Python files:

```
Assignment/
├── api.py            # Backend: FastAPI REST service & core typed LLM prompt functions
├── app.py            # Frontend: Single-page Streamlit interactive application
├── .env              # Environment variables (private API keys)
├── .env.example      # Template documentation for environment variables
├── pyproject.toml    # Dependencies and project metadata (UV-managed)
└── README.md         # Full project documentation and usage guide
```

---

## 🎯 Key Features & Requirements Met

### 1. Structured Inputs (Not Just a Single Text Box)
Collects comprehensive, trainer-level constraints:
* **Fitness Goal**: Dropdown (*Build muscle*, *Lose fat*, *General fitness*, *Improve endurance*)
* **Experience Level**: Dropdown (*Beginner*, *Intermediate*, *Advanced*)
* **Weekly Frequency**: Slider (1 to 7 days per week) with split recommendations
* **Equipment Access**: Multiselect (*No equipment / Bodyweight*, *Home dumbbells*, *Full gym*, *Resistance bands*, *Pull-up bar*, *Kettlebells*)
* **Injuries & Limitations**: Free text with quick one-click chips (*"bad knees"*, *"shoulder pain"*, *"lower back strain"*)
* **Target Session Duration**: Slider (20 to 90 minutes)

### 2. Constraint-Enforced Prompt Design
The core learning goal of the project is rigorous prompt engineering:
* **Equipment Strictness**: The LLM is strictly constrained to prescribe *only* exercises performable with the user's selected equipment.
* **Injury & Joint Safeguards**: Whenever an injury or limitation is given, aggravating movements are eliminated and replaced with joint-friendly biomechanical alternatives (e.g., box squats, Romanian deadlifts, or glute bridges for bad knees).
* **Exact Day Count**: The generated split precisely matches the requested number of training days.
* **Medical & Safety Disclaimer**: Automatically scoped to caution the user, especially when limitations are reported.

### 3. Core Function with Type Hints & Try/Except
In [`api.py`](api.py), the generator function is strictly typed and handles all Groq exceptions gracefully:
```python
def generate_workout_plan(
    fitness_goal: str,
    experience_level: str,
    days_per_week: int,
    equipment_access: Union[List[str], str],
    injuries_limitations: Optional[str] = None,
    session_duration_minutes: int = 45,
    variation_seed: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
```
* Catches `AuthenticationError` (401), `NotFoundError` (404), `APIError` (502), and empty responses (502).

### 4. Robust Error Handling
* **Invalid/Missing Inputs** (e.g. 0 days selected, empty goals): Returns a friendly `HTTP 400`/`422` validation message instead of crashing.
* **Failed API Calls** (invalid key, rate limits, network outages): Caught with friendly UI warnings and status toasts.
* **Fallback Dual Mode**: Streamlit communicates with FastAPI via HTTP; if FastAPI is offline, Streamlit automatically falls back to standalone execution using the local engine in `api.py`.

### 5. Stretch Goals Implemented
* 🔄 **"Regenerate Variation"**: Button to request an alternative split/exercise selection.
* 💾 **Session State Persistence**: Uses `st.session_state` so routines remain intact across page reruns.
* 📥 **Export to File**: One-click download as Markdown (`.md`) or Plain Text (`.txt`).
* 🔍 **"Swap This Exercise" Assistant**: Interactive tool to swap any individual movement based on joint pain, equipment absence, or difficulty.

---

## 🛠️ Setup & Running

### 1. Environment Configuration
Create or edit your `.env` file:
```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-20b
```

### 2. Start the FastAPI Backend
In your first terminal, run:
```bash
uv run uvicorn api:app --reload --port 8000
```
* **Swagger UI (Interactive Docs)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 3. Start the Streamlit Frontend
In your second terminal, run:
```bash
uv run streamlit run app.py
```
* **Streamlit Web App**: [http://127.0.0.1:8501](http://127.0.0.1:8501)

---

## 🧪 Testing the API Directly

You can test the endpoints directly using Python or cURL:

### Generate Plan (`POST /generate-plan`)
```python
import requests

payload = {
    "fitness_goal": "Build muscle",
    "experience_level": "Intermediate",
    "days_per_week": 3,
    "equipment_access": ["Home dumbbells"],
    "injuries_limitations": "bad knees, avoid heavy squats",
    "session_duration_minutes": 45,
}

response = requests.post("http://127.0.0.1:8000/generate-plan", json=payload)
print(response.json()["plan_markdown"])
```

### Swap Exercise (`POST /swap-exercise`)
```python
import requests

payload = {
    "exercise_to_swap": "Barbell Back Squat",
    "reason": "Joint discomfort / bad knees",
    "equipment_access": ["Home dumbbells"],
    "injuries_limitations": "bad knees",
}

response = requests.post("http://127.0.0.1:8000/swap-exercise", json=payload)
print(response.json()["swap_suggestions_markdown"])
```
