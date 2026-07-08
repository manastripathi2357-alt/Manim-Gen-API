# ManimGen API Video Generator

ManimGen API is an AI-powered tool that generates animations and visual scenes based on text prompts. It uses Google's Gemini LLM to write Python scripts for the Manim Community library, which then renders math animations and visual content programmatically.

## Structure
- `main.py`: The FastAPI server backend.
- `generate_scene.py`: Core logic for interacting with Gemini and running the Manim rendering engine.
- `frontend/`: The frontend web application interface.

## Running Locally
1. Create a `.env` file in the root directory and add your Gemini API key:
   ```env
   GEMINI_API_KEY=your_api_key_here
   ```
2. Start the FastAPI backend:
   ```bash
   python main.py
   ```
3. Open `frontend/index.html` in your browser or run a simple local server in the frontend directory.
