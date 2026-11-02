import os
from typing import List, Optional, Union
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from groq import APIError, AuthenticationError, Groq, NotFoundError
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv(override=True)

app = FastAPI(
    title="IronPulse Workout Plan Generator API",
    description="FastAPI backend powered by Groq LLM to generate structured, personalized workout routines with strict constraint enforcement.",
    version="1.0.0",
)

# Enable CORS for local Streamlit and frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# Pydantic Request & Response Models
# ==========================================

class WorkoutPlanRequest(BaseModel):
    fitness_goal: str = Field(
        ...,
        description="User's primary fitness goal (e.g. Build muscle, Lose fat, General fitness, Improve endurance)",
        examples=["Build muscle"],
    )
    experience_level: str = Field(
        ...,
        description="Experience level (Beginner, Intermediate, Advanced)",
        examples=["Intermediate"],
    )
    days_per_week: int = Field(
        ...,
        ge=1,
        le=7,
        description="Number of workout days available per week (1-7)",
        examples=[4],
    )
    equipment_access: Union[List[str], str] = Field(
        ...,
        description="Equipment available (e.g., ['No equipment', 'Home dumbbells', 'Full gym'])",
        examples=[["Home dumbbells", "Pull-up bar"]],
    )
    injuries_limitations: Optional[str] = Field(
        default=None,
        description="Optional injuries, joint pain, or movement limitations (e.g., 'bad knees', 'no overhead pressing')",
        examples=["bad knees, avoid heavy axial loading"],
    )
    session_duration_minutes: Optional[int] = Field(
        default=45,
        ge=15,
        le=120,
        description="Target workout duration in minutes per session",
        examples=[45],
    )
    variation_seed: Optional[str] = Field(
        default=None,
        description="Optional variation tag or seed for generating alternative workout splits",
    )


class WorkoutPlanResponse(BaseModel):
    success: bool
    fitness_goal: str
    experience_level: str
    days_per_week: int
    equipment_access: List[str]
    injuries_noted: bool
    plan_markdown: str
    model_used: str


class ExerciseSwapRequest(BaseModel):
    exercise_to_swap: str = Field(..., description="The exercise the user wishes to replace", examples=["Barbell Back Squat"])
    reason: str = Field(..., description="Reason for replacement (e.g. 'bad knees', 'no barbell', 'too difficult')", examples=["Knee pain when going deep"])
    equipment_access: Union[List[str], str] = Field(..., description="Available equipment")
    injuries_limitations: Optional[str] = Field(default=None, description="Known physical limitations")


class ExerciseSwapResponse(BaseModel):
    success: bool
    original_exercise: str
    swap_suggestions_markdown: str
    model_used: str


# ==========================================
# Core LLM Prompting & Logic Functions
# ==========================================

def get_groq_client(api_key_override: Optional[str] = None) -> Groq:
    """Retrieve and validate the Groq client instance."""
    api_key = api_key_override or os.getenv("GROQ_API_KEY")
    if not api_key or api_key.strip() in ("", "<api-key>", "your_groq_api_key_here"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Missing GROQ_API_KEY in environment. Please set GROQ_API_KEY in your .env file or UI settings.",
        )
    return Groq(api_key=api_key.strip())


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
    """
    Take structured fitness parameters, construct an engineered prompt adhering strictly
    to user constraints, invoke the Groq LLM, and return a formatted workout routine.

    Raises:
        HTTPException with proper HTTP status codes for validation and API failures.
    """
    # 1. Input Validation
    if not fitness_goal or not fitness_goal.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Fitness goal cannot be empty.")

    if not experience_level or not experience_level.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Experience level cannot be empty.")

    if not (1 <= days_per_week <= 7):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Days available per week must be between 1 and 7.")

    # Normalize equipment representation
    if isinstance(equipment_access, list):
        equipment_str = ", ".join(equipment_access) if equipment_access else "No equipment (Bodyweight only)"
    else:
        equipment_str = str(equipment_access).strip() or "No equipment (Bodyweight only)"

    injuries_str = (injuries_limitations or "").strip()
    has_injuries = bool(injuries_str and injuries_str.lower() not in ["none", "no", "n/a", "nil"])

    # 2. Setup Groq Client and Model
    client = get_groq_client(api_key_override=api_key)
    target_model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")


    # 3. Carefully Engineered System Prompt
    system_prompt = (
        "You are an elite Certified Strength and Conditioning Specialist (CSCS) and physical preparation coach. "
        "Your mission is to construct an actionable, scientifically sound, and safe weekly workout routine tailored to the client's parameters.\n\n"
        "STRICT NON-NEGOTIABLE CONSTRAINTS:\n"
        "1. RESPECT EQUIPMENT ACCESS: Prescribe ONLY exercises performable with the specified equipment. "
        "If 'No equipment', prescribe ONLY calisthenics/bodyweight movements. If 'Home dumbbells', do not include barbell or cable machine exercises.\n"
        "2. INJURIES & LIMITATIONS (CRITICAL): If the client notes any injury or limitation, NEVER prescribe exercises that aggravate or load that area. "
        "Explicitly substitute safer biomechanical alternatives and note why (e.g. for bad knees, use box squats, Romanian deadlifts, or glute bridges instead of deep lunges; for shoulder pain, use neutral grip DB presses or lateral raises instead of barbell overhead pressing).\n"
        "3. EXACT DAY COUNT: You must provide a structured schedule for EXACTLY the number of training days requested (no more, no less). "
        "Distribute days logically (e.g., 3 days = Full Body A/B/C or Push/Pull/Legs; 4 days = Upper/Lower; 5 days = Upper/Lower/PPL).\n"
        "4. OUTPUT FORMATTING: Use clean, well-spaced Markdown:\n"
        "   - ## 🎯 Routine Overview & Split Schedule (Show Day 1 through Day N, and active recovery guidance)\n"
        "   - Day by Day Breakdown:\n"
        "     - ### Day X: [Focus Title] (~[Duration] mins)\n"
        "     - **Dynamic Warm-Up** (3-5 mins, 2-3 specific mobility movements)\n"
        "     - **Workout Table**: Markdown table with columns: `| Exercise | Target Muscle | Sets | Reps / Duration | Rest | Key Form Cue |`\n"
        "     - **Cool-Down & Mobility** (3-5 mins)\n"
        "   - ## 📈 Progression Strategy & Recovery Guidance\n"
        "   - ## ⚠️ Health & Safety Disclaimer: Mandatory. State clearly that this is an AI-generated fitness program and not medical advice. "
        "Highlight safety precautions particularly around any listed limitations.\n"
        "5. COMPLETENESS: Be concise, clear, and ensure every single section (all days, progression notes, and disclaimer) is fully completed without running out of tokens."
    )

    # 4. User Prompt
    variation_note = f"\n- Variation Request: Please provide a distinct, fresh variation/split strategy ({variation_seed})." if variation_seed else ""

    user_prompt = f"""Generate a personalized weekly workout plan for this client:

- Primary Fitness Goal: {fitness_goal}
- Experience Level: {experience_level}
- Weekly Frequency: {days_per_week} days per week
- Target Session Length: {session_duration_minutes} minutes
- Equipment Available: {equipment_str}
- Physical Limitations / Injuries: {injuries_str if has_injuries else "None reported"}{variation_note}

Requirements:
- Prescribe exactly {days_per_week} dedicated workout days.
- Use a clean Markdown table for each workout day.
- Strictly adhere to equipment and injury constraints.
- Conclude with a safety/medical disclaimer.
- Keep descriptions crisp so the entire routine completes seamlessly."""

    # 5. Groq API Call with robust error handling matching user style
    try:
        completion = client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7 if not variation_seed else 0.85,
            max_tokens=3500,
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Groq API key. Check GROQ_API_KEY in .env or sidebar settings.",
        ) from e
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Groq model '{target_model}' not found. Please choose a valid Groq model.",
        ) from e
    except APIError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Groq API error: {e.message}",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error communicating with LLM: {str(e)}",
        ) from e

    plan = completion.choices[0].message.content
    if not plan or not plan.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM returned an empty workout plan response.",
        )

    return plan.strip()


def swap_workout_exercise(
    exercise_to_swap: str,
    reason: str,
    equipment_access: Union[List[str], str],
    injuries_limitations: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    Suggest targeted exercise substitutions matching equipment and injury constraints.
    """
    if not exercise_to_swap.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exercise name cannot be empty.")

    equipment_str = ", ".join(equipment_access) if isinstance(equipment_access, list) else str(equipment_access)
    client = get_groq_client(api_key_override=api_key)
    target_model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

    system_prompt = (
        "You are an expert biomechanics specialist and fitness coach. "
        "Provide 3 high-quality substitute exercises for the specified movement. "
        "All suggestions MUST respect the user's available equipment and limitation reasons. "
        "Format as Markdown with: Exercise Name, Why It Works, Sets/Reps suggestion, and a safety tip."
    )

    user_prompt = f"""I need to swap out the following exercise:
- Current Exercise: {exercise_to_swap}
- Reason for swap: {reason}
- Available Equipment: {equipment_str}
- Physical Limitations: {injuries_limitations or 'None'}

Please provide 3 alternative exercises that target the same movement pattern/muscles safely."""

    try:
        completion = client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.6,
            max_tokens=800,
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail="Invalid Groq API key.") from e
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Model '{target_model}' not found.") from e
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"Groq API error: {e.message}") from e

    content = completion.choices[0].message.content
    if not content:
        raise HTTPException(status_code=502, detail="LLM returned empty swap alternatives.")
    return content.strip()


# ==========================================
# FastAPI API Endpoints
# ==========================================

@app.get("/")
def read_root():
    """Root status check."""
    return {
        "service": "IronPulse Workout Plan Generator API",
        "status": "online",
        "docs_url": "/docs",
        "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
    }


@app.get("/health")
def health_check():
    """Health check endpoint to test connectivity and key presence."""
    has_key = bool(os.getenv("GROQ_API_KEY") and os.getenv("GROQ_API_KEY") != "<api-key>")
    return {
        "status": "healthy",
        "groq_api_key_configured": has_key,
        "default_model": os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
    }


@app.post("/generate-plan", response_model=WorkoutPlanResponse)
def api_generate_workout_plan(request: WorkoutPlanRequest):
    """
    POST endpoint to generate a personalized weekly workout plan.
    Accepts structured client parameters and returns formatted Markdown.
    """
    equip_list = request.equipment_access if isinstance(request.equipment_access, list) else [request.equipment_access]
    plan_text = generate_workout_plan(
        fitness_goal=request.fitness_goal,
        experience_level=request.experience_level,
        days_per_week=request.days_per_week,
        equipment_access=equip_list,
        injuries_limitations=request.injuries_limitations,
        session_duration_minutes=request.session_duration_minutes or 45,
        variation_seed=request.variation_seed,
    )

    model_used = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    injuries_present = bool(request.injuries_limitations and request.injuries_limitations.strip())

    return WorkoutPlanResponse(
        success=True,
        fitness_goal=request.fitness_goal,
        experience_level=request.experience_level,
        days_per_week=request.days_per_week,
        equipment_access=equip_list,
        injuries_noted=injuries_present,
        plan_markdown=plan_text,
        model_used=model_used,
    )


@app.post("/swap-exercise", response_model=ExerciseSwapResponse)
def api_swap_exercise(request: ExerciseSwapRequest):
    """
    POST endpoint to get biomechanically safe substitutions for an individual exercise.
    """
    equip_list = request.equipment_access if isinstance(request.equipment_access, list) else [request.equipment_access]
    swap_suggestions = swap_workout_exercise(
        exercise_to_swap=request.exercise_to_swap,
        reason=request.reason,
        equipment_access=equip_list,
        injuries_limitations=request.injuries_limitations,
    )

    model_used = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

    return ExerciseSwapResponse(
        success=True,
        original_exercise=request.exercise_to_swap,
        swap_suggestions_markdown=swap_suggestions,
        model_used=model_used,
    )


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("FASTAPI_HOST", "127.0.0.1")
    port = int(os.getenv("FASTAPI_PORT", "8000"))
    uvicorn.run("api:app", host=host, port=port, reload=True)
