import os
import re
import sys
import time
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from google import genai

# 1. Load the environment variables from the .env file
load_dotenv()

# 1.5 Fix Mac Path issue so Manim can find LaTeX (BasicTeX)
os.environ["PATH"] += os.pathsep + "/Library/TeX/texbin"

# 2. Initialize the Gemini client using the NEW SDK
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def ask_ai_for_manim_code(user_prompt):
    # --- PROMPT ENGINEERING: THE RULES ---
    system_instruction = (
        "You are an expert in Python and the Manim Community Edition animation library. "
        "When given a request, generate ONLY valid Python code using Manim. "
        "Do not include any explanations, greetings, or markdown formatting outside the code block. "
        "CRITICAL RULES: "
        "1. IMPORTS: Always start with `from manim import *`. "
        "2. FONTS AND TEXT: Use `MathTex()` for all mathematical equations and formulas. "
        "   Use `Text()` for standard text. "
        "   When using `MathTex`, ensure your LaTeX strings are properly formatted (e.g., using raw strings like `r\"\\frac{1}{2}\"`). "
        "3. ANIMATIONS: Always use `self.play()` to animate objects appearing on screen (e.g., `self.play(Create(obj))`, `self.play(Write(text))`). "
        "   Do not simply use `self.add()` unless you want the object to appear instantly without animation. "
        "   Use `self.wait()` between logical steps to give the viewer time to read. "
        "4. 3D SCENES: If the prompt requires 3D, inherit from `ThreeDScene` instead of `Scene`. "
        "   Always call `self.set_camera_orientation(phi=75 * DEGREES, theta=30 * DEGREES)` at the beginning of the `construct` method to set a good viewing angle. "
        "   CRITICAL: `self.camera` does NOT have an `.animate` attribute! To animate the camera in a ThreeDScene, you MUST use `self.move_camera(phi=..., theta=..., run_time=...)`. "
        "5. LAYOUT: Ensure objects are properly spaced out using `.next_to()`, `.move_to()`, or `.shift()` so they do not overlap. "
        "6. RATE FUNCTIONS: If you use a rate function, use `rate_functions.smooth`, `rate_functions.linear`, etc. DO NOT use rate_func names without the `rate_functions.` prefix. "
        "7. ONLY Output the raw python code block. No preamble, no postamble."
    )

    full_prompt = f"{system_instruction}\n\nUser Request: {user_prompt}"
    
    max_api_retries = 3
    for attempt in range(max_api_retries):
        try:
            print(f"Sending prompt to Gemini, please wait...")
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=full_prompt,
            )
            return response.text
        except Exception as e:
            if "429" in str(e) or "503" in str(e):
                print(f"API Rate limit hit! Waiting 60 seconds before retrying (Attempt {attempt+1}/{max_api_retries})...")
                time.sleep(60)
            else:
                raise e
    raise Exception("Failed to get response from Gemini after multiple rate limit retries.")

def extract_python_code(raw_text):
    # Using chr(96) to generate backticks safely without breaking the chat UI
    backticks = chr(96) * 3
    pattern = rf"{backticks}(?:python)?\n(.*?)\n{backticks}"
    match = re.search(pattern, raw_text, re.DOTALL)
    
    if match:
        return match.group(1).strip()
    return raw_text.strip()

def update_task_status(task_id: str, status: str, video_url: str = None, error: str = None, code: str = None):
    if not task_id:
        return
    from database import SessionLocal
    from models import Task
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = status
            if video_url:
                task.video_url = video_url
            if error:
                task.error = error
            if code:
                task.code = code
            db.commit()
    finally:
        db.close()

def generate_animation_video(user_request: str, task_id: str = None) -> str:
    try:
        result = ask_ai_for_manim_code(user_request)
        cleaned_code = extract_python_code(result)
    
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"animation_{timestamp}.py"
        
        with open(output_filename, "w") as f:
            f.write(cleaned_code)
        
        print(f"Success! Saved as -> {output_filename}")
    
        # --- Automated Pipeline and Retry Logic ---
        max_retries = 3
        current_try = 0
        success = False
        filename = output_filename
    
        while current_try < max_retries and not success:
            print(f"\n--- Attempt {current_try + 1} ---")
    
            # Render using Manim (-qm for 720p30). Removed -p so the server doesn't pop up videos.
            result = subprocess.run(    
                [sys.executable, "-m", "manim", "-qm", "-v", "WARNING", filename],
                capture_output=True,
                text=True
            )
    
            if result.returncode == 0:
                print("Successfully rendered!")
                success = True
            else:
                print("Error detected in AI output. Asking Gemini to fix it...")
    
                fix_prompt = f"""Original User Request: {user_request}
    Generated Manim Code: 
    ```python
    {cleaned_code}
    ```
    Error Message:
    {result.stderr}
    
    The above Manim code failed to render. Please fix all syntax, logic, and Manim-related errors.
    Read the stack trace carefully and ONLY change the code necessary to fix the crash. Do not unnecessarily rewrite the entire scene.
    
    CRITICAL REMINDERS:
    1. Use `MathTex()` for math and `Text()` for standard text. Ensure valid LaTeX syntax for MathTex.
    2. Ensure you are using Manim Community Edition syntax.
    3. Fix any missing variables or undefined names mentioned in the error.
    4. If the error is a NameError about a rate function (like ease_out_quad), prefix it with `rate_functions.` (e.g. `rate_functions.ease_out_quad`).
    5. ONLY return the corrected Python code inside triple backticks (```python). No explanations.
    """
    
                try:
                    # Ask Gemini for corrected code
                    fixed_response = ask_ai_for_manim_code(fix_prompt)
                    cleaned_code = extract_python_code(fixed_response)
    
                    with open(filename, "w") as f:
                        f.write(cleaned_code)
    
                    print("Corrected code saved. Retrying render...")
                except Exception as e:
                    print(f"Failed to get corrected code: {e}")
                    break
    
                current_try += 1
    
        if not success:
            error_msg = f"Failed to generate animation after {max_retries} attempts. Check {filename}."
            update_task_status(task_id, "failed", error=error_msg)
            raise Exception(error_msg)
    
        # Find and return the path to the generated mp4 video
        script_name = output_filename.replace(".py", "")
        video_dir = os.path.join("media", "videos", script_name, "720p30")
        
        if os.path.exists(video_dir):
            mp4_files = [f for f in os.listdir(video_dir) if f.endswith(".mp4")]
            if mp4_files:
                video_url = f"/media/videos/{script_name}/720p30/{mp4_files[0]}"
                update_task_status(task_id, "completed", video_url=video_url, code=cleaned_code)
                return video_url
                
        error_msg = "Video rendered, but MP4 file was not found in the media directory."
        update_task_status(task_id, "failed", error=error_msg)
        raise Exception(error_msg)
    
    except Exception as e:
        update_task_status(task_id, "failed", error=str(e))
        raise e

# --- Interactive Terminal Block ---
if __name__ == "__main__":
    print("\n" + "="*50)
    print("Welcome to the Bulletproof AI Animation Generator!")
    print("Type your idea, or type 'quit' to exit.")
    print("="*50)
    
    while True:
        user_request = input("\nEnter your animation idea: ")
        if user_request.lower() in ['quit', 'exit']:
            print("Shutting down. Goodbye!")
            break
        if user_request.strip() == "":
            continue
            
        try:
            video_url = generate_animation_video(user_request)
            print(f"\n[DONE] Video available at: {video_url}")
            
            # If running in terminal, auto-open it on Mac
            subprocess.run(["open", "." + video_url])
        except Exception as e:
            print(f"Error: {e}")