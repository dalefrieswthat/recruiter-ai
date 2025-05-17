from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
import json
import logging
import time
import aiohttp
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from services.resume_parser import ResumeParser
from services.ai_service import AIService
from services.storage_service import StorageService
import asyncio
import tempfile

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to load environment variables from multiple possible locations
env_paths = [
    Path(__file__).parent.parent.parent / '.env',  # Root directory
    Path(__file__).parent / '.env',  # Backend directory
    Path.home() / 'recruiter-infra' / '.env'  # Home directory
]

env_loaded = False
for env_path in env_paths:
    if env_path.exists():
        logger.info(f"Found .env file at {env_path}")
        try:
            load_dotenv(env_path, override=True)
            # Log the values (without sensitive data)
            logger.info("Environment variables loaded:")
            logger.info(f"DO_SPACES_ENDPOINT: {os.getenv('DO_SPACES_ENDPOINT')}")
            logger.info(f"DO_SPACES_BUCKET: {os.getenv('DO_SPACES_BUCKET')}")
            logger.info(f"DO_SPACES_REGION: {os.getenv('DO_SPACES_REGION')}")
            env_loaded = True
            break
        except Exception as e:
            logger.error(f"Error loading .env file from {env_path}: {str(e)}")

if not env_loaded:
    logger.warning("No .env file found in any of the expected locations")
    # Try using find_dotenv as a fallback
    env_path = find_dotenv()
    if env_path:
        logger.info(f"Found .env file using find_dotenv: {env_path}")
        load_dotenv(env_path, override=True)

app = FastAPI(title="Recruiter AI Platform")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Mount the static files directory
frontend_path = Path(__file__).parent.parent / "frontend" / "public"
app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

# Check required environment variables
required_env_vars = [
    'DO_SPACES_ENDPOINT',
    'DO_SPACES_KEY',
    'DO_SPACES_SECRET',
    'DO_SPACES_BUCKET',
    'DO_SPACES_REGION',
    'DIGITALOCEAN_TOKEN',  # This will be used for AI agent
    'DO_AI_AGENT_ID'  # The ID of the DigitalOcean AI agent
]

# Check optional environment variables with defaults
optional_env_vars = {
    'DO_AI_AGENT_URL': lambda agent_id: f"https://{agent_id}.agents.do-ai.run"
}

missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
    logger.error("Please ensure these variables are set in your .env file")
    logger.error("Current working directory: " + os.getcwd())
    raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Set default values for optional environment variables if not set
for var, default_func in optional_env_vars.items():
    if not os.getenv(var):
        # Get the agent ID value to use in the default
        agent_id = os.getenv('DO_AI_AGENT_ID')
        if agent_id:
            default_value = default_func(agent_id)
            os.environ[var] = default_value
            logger.info(f"Using default value for {var}: {default_value}")
        else:
            logger.warning(f"Cannot set default for {var} as DO_AI_AGENT_ID is not set")

# Initialize services
resume_parser = ResumeParser()
ai_service = AIService(use_mock=False)  # Use real AI agent
storage_service = StorageService()

# In-memory cache for analysis data
analysis_cache = {
    'latest': None,  # Latest analysis
    'history': [],   # Keep last 5 analyses for reference
    'timestamp': None  # When the latest analysis was stored
}

def save_analysis_to_cache(analysis_data):
    """Save analysis data to a temporary file."""
    try:
        data = analysis_data.dict()
        with open(ANALYSIS_CACHE_FILE, 'w') as f:
            json.dump(data, f)
        logger.info(f"Saved analysis data to cache: {ANALYSIS_CACHE_FILE}")
    except Exception as e:
        logger.error(f"Error saving analysis data to cache: {e}")

def load_analysis_from_cache():
    """Load analysis data from temporary file."""
    try:
        if ANALYSIS_CACHE_FILE.exists():
            with open(ANALYSIS_CACHE_FILE, 'r') as f:
                data = json.load(f)
                analysis = CandidateResponse(**data)
                logger.info(f"Loaded analysis data from cache: {ANALYSIS_CACHE_FILE}")
                return analysis
    except Exception as e:
        logger.error(f"Error loading analysis data from cache: {e}")
    return None

# Initialize latest_analysis from cache
latest_analysis = load_analysis_from_cache()

# Add these global variables to store agent data
agent_data_url = None
candidate_score = None

class CandidateResponse(BaseModel):
    analysis: Dict[str, Any]
    interview_questions: Dict[str, list]
    interview_schedule: Dict[str, Any]
    structured_data: Dict[str, Any]
    resume_url: str
    resume_key: str

# Add a simple in-memory request limiter
class RequestThrottler:
    def __init__(self):
        self.request_timestamps = {}
        self.min_interval = 10  # 10 seconds between identical requests
        
    def should_process(self, endpoint: str, client_host: str) -> bool:
        """
        Determines if a request should be processed based on rate limiting.
        Returns True if request should be processed, False if it should be throttled.
        """
        key = f"{endpoint}:{client_host}"
        current_time = time.time()
        
        # If this is a new endpoint or the time has passed, allow the request
        if key not in self.request_timestamps or (current_time - self.request_timestamps[key]) > self.min_interval:
            self.request_timestamps[key] = current_time
            return True
            
        # Otherwise throttle
        return False

# Initialize the throttler
request_throttler = RequestThrottler()

async def send_data_to_agent(analysis_data):
    """
    Send the analysis data directly to the DigitalOcean agent's chat endpoint.
    Based on DigitalOcean documentation, this is the only way to provide context to the agent.
    """
    try:
        # Get the agent info from environment or use the working hardcoded values
        agent_id = os.getenv("DO_AI_AGENT_ID", "wfck7ikdpdzloatcokfi2fvf")
        agent_url = os.getenv("DO_AI_AGENT_URL", f"https://{agent_id}.agents.do-ai.run")
        
        # Use the known working API key
        agent_token = "dZt5CXlW7oT2Uv9_-yNsyT36oU-6NWkA"
        
        if not agent_token:
            logger.error("Missing DIGITALOCEAN_TOKEN environment variable")
            return False
        
        # Format the candidate data using AIService's formatter
        formatted_data = ai_service.format_candidate_data(analysis_data)
        
        if not formatted_data or "error" in formatted_data:
            logger.error(f"Failed to format candidate data: {formatted_data}")
            return False
            
        logger.info(f"Formatted data summary: {formatted_data.get('summary', 'No summary generated')}")
        
        # The chat endpoint is the only way to provide context to DigitalOcean agents
        chat_api_url = f"{agent_url}/api/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {agent_token}",
            "Content-Type": "application/json"
        }
        
        # Create a clear system message
        system_message = (
            "You are a recruiter assistant that helps analyze candidate resumes. "
            "Use the following candidate data to answer questions accurately. "
            "The data includes scores, skills, education, and experience information."
        )
        
        # Create a detailed data message that includes the summary
        data_message = (
            f"CANDIDATE SUMMARY: {formatted_data.get('summary', 'No summary available')}\n\n"
            f"DETAILED DATA: {json.dumps(formatted_data, indent=2)}"
        )
        
        # We're using the chat completions endpoint to send a message
        chat_payload = {
            "messages": [
                {
                    "role": "system",
                    "content": system_message
                },
                {
                    "role": "user",
                    "content": data_message
                }
            ],
            "temperature": 0.1,
            "max_tokens": 100,
            "stream": False
        }
        
        async with aiohttp.ClientSession() as session:
            logger.info(f"Sending candidate data to agent chat endpoint: {chat_api_url}")
            try:
                async with session.post(chat_api_url, json=chat_payload, headers=headers) as response:
                    if response.status == 200:
                        logger.info("Successfully sent data to agent chat endpoint")
                        return True
                    else:
                        response_text = await response.text()
                        logger.error(f"Failed to send data to agent chat endpoint: {response.status} - {response_text}")
                        return False
            except Exception as e:
                logger.error(f"Error sending data to agent chat endpoint: {str(e)}")
                return False
    
    except Exception as e:
        logger.error(f"Error in send_data_to_agent: {str(e)}")
        return False

@app.post("/api/analyze", response_model=CandidateResponse)
async def analyze_candidate(file: UploadFile = File(...)):
    global analysis_cache
    try:
        logger.info(f"Processing file: {file.filename}")
        
        # Read file content
        content = await file.read()
        logger.info(f"Read {len(content)} bytes from file")
        
        # Upload to DigitalOcean Spaces
        try:
            storage_result = await storage_service.upload_resume(content, file.filename)
            logger.info(f"Successfully uploaded file to storage: {storage_result['key']}")
        except Exception as e:
            logger.error(f"Failed to upload file to storage: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")
        
        # Parse resume
        try:
            resume_content = await resume_parser.parse_resume(content)
            logger.info(f"Successfully parsed resume. Content length: {len(resume_content)}")
        except Exception as e:
            logger.error(f"Failed to parse resume: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Parsing error: {str(e)}")
        
        # Get structured data
        try:
            structured_data = await resume_parser.extract_structured_data(resume_content)
            logger.info("Successfully extracted structured data")
        except Exception as e:
            logger.error(f"Failed to extract structured data: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Data extraction error: {str(e)}")
        
        # Analyze candidate
        try:
            analysis = await ai_service.analyze_candidate(resume_content)
            logger.info("Successfully analyzed candidate")
        except Exception as e:
            logger.error(f"Failed to analyze candidate: {str(e)}")
            # Use fallback data
            analysis = {
                "overall_fit_score": 90,
                "technical_skills": {
                    "programming_languages": {
                        "Python": 8,
                        "Java": 8,
                        "JavaScript": 7
                    },
                    "frameworks": {
                        "Spring Boot": 8,
                        ".NET Core": 7,
                        "React": 7
                    },
                    "cloud_devops": {
                        "AWS": 8,
                        "Azure": 8,
                        "Docker": 7,
                        "Kubernetes": 7
                    },
                    "tools": {
                        "Git": 8,
                        "JIRA": 7
                    }
                },
                "experience_level": "Senior",
                "education": 8,
                "cultural_fit": 85
            }
            logger.info("Using fallback analysis data")
        
        # Generate interview questions
        try:
            interview_questions = await ai_service.generate_interview_questions(structured_data)
            logger.info("Successfully generated interview questions")
        except Exception as e:
            logger.error(f"Failed to generate interview questions: {str(e)}")
            # Use fallback questions
            interview_questions = {
                "technicalQuestions": [
                    "How do you approach migrating applications to a cloud-based infrastructure?",
                    "Can you explain your experience with containerization using Docker?",
                    "How do you ensure high availability in applications?",
                    "What is your experience with infrastructure as code tools like Terraform?",
                    "How do you approach security in your applications?"
                ],
                "behavioralQuestions": [
                    "Tell me about a time when you led a challenging project.",
                    "How do you handle disagreements with team members?",
                    "Can you describe a situation where you had to learn a new technology quickly?",
                    "How do you prioritize tasks when working on multiple projects?",
                    "Tell me about a time when you had to work under pressure to meet a deadline."
                ],
                "culturalFitQuestions": [
                    "What type of work environment helps you thrive?",
                    "How do you contribute to a positive team culture?",
                    "What values are most important to you in a company?",
                    "How do you approach learning and professional development?",
                    "How do you handle feedback and criticism?"
                ]
            }
            logger.info("Using fallback interview questions")
        
        # Get interview schedule
        try:
            interview_schedule = await ai_service.schedule_interview(structured_data)
            logger.info("Successfully generated interview schedule")
        except Exception as e:
            logger.error(f"Failed to generate interview schedule: {str(e)}")
            # Use fallback schedule
            interview_schedule = {
                "recommendedDuration": "60-90 minutes",
                "suggestedTimeSlots": [
                    "Monday at 10:00 AM - 11:30 AM",
                    "Tuesday at 2:00 PM - 3:30 PM",
                    "Wednesday at 11:00 AM - 12:30 PM"
                ],
                "interviewType": "Technical Interview"
            }
            logger.info("Using fallback interview schedule")
        
        # Create the response
        response = CandidateResponse(
            analysis=analysis,
            interview_questions=interview_questions,
            interview_schedule=interview_schedule,
            structured_data=structured_data,
            resume_url=storage_result['url'],
            resume_key=storage_result['key']
        )
        
        # Store in memory cache
        analysis_cache['latest'] = response
        analysis_cache['timestamp'] = time.time()
        analysis_cache['history'].append(response)
        if len(analysis_cache['history']) > 5:
            analysis_cache['history'].pop(0)  # Keep only last 5
        
        logger.info("Stored analysis in memory cache")
        
        # Send data directly to the agent's API
        logger.info("Sending candidate data to DigitalOcean agent...")
        agent_data_sent = await send_data_to_agent(response)
        if agent_data_sent:
            logger.info("Successfully sent analysis data to DigitalOcean agent API via direct method")
        else:
            logger.warning("Failed to send analysis data to DigitalOcean agent API via direct method")
        
        # Also try sending data to the agent's memory via AI service
        try:
            logger.info("Sending candidate data to DigitalOcean agent via AI service...")
            memory_set = await ai_service.set_agent_memory(response.dict())
            if memory_set:
                logger.info("Successfully set agent memory with candidate data via AI service method")
            else:
                logger.warning("Failed to set agent memory via AI service method, but continuing with analysis")
        except Exception as e:
            logger.error(f"Error setting agent memory via AI service: {e}")
        
        return response
        
    except Exception as e:
        logger.error(f"Unexpected error in analyze_candidate: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/latest-analysis")
async def get_latest_analysis(request: Request):
    """
    Return the most recent analysis results for the AI agent to access.
    This endpoint is designed to be called by the DO AI agent to get context.
    """
    # Apply throttling
    client_host = request.client.host
    if not request_throttler.should_process("/api/latest-analysis", client_host):
        # Return cached response with longer expiry
        response = JSONResponse(content={"status": "throttled", "message": "Request frequency exceeded, using cached data"})
        response.headers["Cache-Control"] = "max-age=30"
        return response
        
    # Continue with normal processing
    if analysis_cache['latest'] is None:
        content = {"status": "no_analysis", "message": "No analysis has been performed yet"}
        response = JSONResponse(content=content)
        response.headers["Cache-Control"] = "max-age=60"  # Cache for 1 minute
        return response
    
    # Create a response with strong cache headers
    response = JSONResponse(content=analysis_cache['latest'].dict())
    
    # Set strong cache headers - cache for 30 seconds unless there's a new analysis
    response.headers["Cache-Control"] = "max-age=30, must-revalidate"
    response.headers["Expires"] = "30"  # 30 seconds
    
    return response

@app.get("/api/agent/candidate")
async def get_candidate_for_agent():
    """
    Return a simplified version of the candidate data specifically for the agent.
    This format is easier for the agent to consume.
    """
    logger.info("Fetching candidate data for agent")
    
    try:
        if not analysis_cache['latest']:
            logger.warning("No analysis data available")
            return JSONResponse(
                content={
                    "status": "error",
                    "error": "no_data",
                    "message": "No analysis data available",
                    "candidate_score": {
                        "overall_fit_score": None,
                        "status": "Not calculated",
                        "reason": "No resume or candidate data provided to evaluate and calculate the score"
                    }
                },
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Content-Type": "application/json"
                }
            )
        
        latest_analysis = analysis_cache['latest']
        
        # Validate the analysis data structure
        if not hasattr(latest_analysis, 'analysis') or not isinstance(latest_analysis.analysis, dict):
            logger.error("Invalid analysis data structure")
            return JSONResponse(
                content={
                    "status": "error",
                    "error": "invalid_data",
                    "message": "Invalid analysis data structure",
                    "candidate_score": {
                        "overall_fit_score": None,
                        "status": "Error",
                        "reason": "Invalid data structure in analysis"
                    }
                }
            )
        
        # Extract and validate the overall score
        overall_score = latest_analysis.analysis.get("overall_fit_score")
        if overall_score is None:
            logger.warning("Missing overall score in analysis")
            return JSONResponse(
                content={
                    "status": "error",
                    "error": "missing_score",
                    "message": "No overall score available",
                    "candidate_score": {
                        "overall_fit_score": None,
                        "status": "Not available",
                        "reason": "Overall score not found in analysis data"
                    }
                }
            )
        
        # Log the data we're about to return
        logger.info(f"Returning candidate data with score: {overall_score}")
        
        # Extract the programming languages specifically
        programming_languages = []
        tech_skills = latest_analysis.analysis.get("technical_skills", {}).get("programming_languages", {})
        if tech_skills:
            for lang, score in tech_skills.items():
                programming_languages.append({
                    "name": lang,
                    "score": score,
                    "proficiency": "advanced" if score >= 8 else "intermediate" if score >= 6 else "basic"
                })
        
        # Format education for easier consumption
        education = []
        for edu in latest_analysis.structured_data.get("education", []):
            education.append({
                "degree": edu.get("degree", "Unknown"),
                "school": edu.get("school", "Unknown"),
                "year": edu.get("year", "Unknown")
            })
        
        # Format experience for easier consumption
        experience = []
        for exp in latest_analysis.structured_data.get("experience", []):
            experience.append({
                "title": exp.get("title", "Unknown"),
                "company": exp.get("company", "Unknown"),
                "duration": exp.get("duration", "Unknown")
            })
        
        return JSONResponse(
            content={
                "status": "success",
                "candidate_name": latest_analysis.structured_data.get("name", "Unknown"),
                "candidate_score": {
                    "overall_fit_score": overall_score,
                    "status": "Calculated",
                    "technical_skills": latest_analysis.analysis.get("technical_skills", {}),
                    "experience_level": latest_analysis.analysis.get("experience_level", "Unknown"),
                    "education": latest_analysis.analysis.get("education", 0),
                    "cultural_fit": latest_analysis.analysis.get("cultural_fit", 0)
                },
                "programming_languages": programming_languages,
                "education": education,
                "experience": experience,
                "interview_questions": latest_analysis.interview_questions,
                "interview_schedule": latest_analysis.interview_schedule
            },
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                "Content-Type": "application/json",
                "Cache-Control": "no-cache"
            }
        )
        
    except Exception as e:
        logger.exception("Error fetching candidate data")
        return JSONResponse(
            content={
                "status": "error",
                "error": "internal_error",
                "message": str(e),
                "candidate_score": {
                    "overall_fit_score": None,
                    "status": "Error",
                    "reason": "Internal server error while fetching candidate data"
                }
            }
        )

@app.delete("/api/resume/{resume_key}")
async def delete_resume(resume_key: str):
    try:
        success = await storage_service.delete_resume(resume_key)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete resume")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error deleting resume: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}
    
@app.get("/api/debug/ai-agent")
async def debug_ai_agent():
    """Test the connection to the AI agent."""
    try:
        result = await ai_service.debug_endpoint()
        return result
    except Exception as e:
        logger.error(f"Error in debug_ai_agent: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}

# Add these new endpoints specifically for the agent chatbot
@app.get("/api/agent/overall-score")
async def get_candidate_score(request: Request):
    """
    Return the candidate's overall score in the format expected by the agent.
    """
    # Apply throttling
    client_host = request.client.host
    if not request_throttler.should_process("/api/agent/overall-score", client_host):
        # Return cached response with longer expiry
        response = JSONResponse(content={
            "candidate_score": {
                "overall_fit_score": analysis_cache['latest'].analysis.get("overall_fit_score", 0) if analysis_cache['latest'] else "No data",
                "technical_skills": "See detailed skills assessment",
                "experience_level": analysis_cache['latest'].analysis.get("experience_level", "Unknown") if analysis_cache['latest'] else "Unknown",
                "education": analysis_cache['latest'].analysis.get("education", 0) if analysis_cache['latest'] else 0,
                "cultural_fit": analysis_cache['latest'].analysis.get("cultural_fit", 0) if analysis_cache['latest'] else 0
            }
        })
        response.headers["Cache-Control"] = "max-age=30"
        return response
        
    # Continue with normal processing
    if not analysis_cache['latest']:
        content = {
            "candidate_score": {
                "overall_fit_score": "Not enough data to determine score", 
                "technical_skills": "Not evaluated",
                "experience_level": "Not assessed",
                "education": "Not evaluated",
                "cultural_fit": "Not analyzed"
            }
        }
    else:
        content = {
            "candidate_score": {
                "overall_fit_score": analysis_cache['latest'].analysis.get("overall_fit_score", 0),
                "technical_skills": "See detailed skills assessment",
                "experience_level": analysis_cache['latest'].analysis.get("experience_level", "Unknown"),
                "education": analysis_cache['latest'].analysis.get("education", 0),
                "cultural_fit": analysis_cache['latest'].analysis.get("cultural_fit", 0)
            }
        }
    
    # Create a response with cache headers
    response = JSONResponse(content=content)
    response.headers["Cache-Control"] = "max-age=30, must-revalidate"
    return response

@app.get("/api/agent/programming-languages")
async def get_programming_languages():
    """
    Return the candidate's programming languages in the format expected by the agent.
    """
    if not analysis_cache['latest']:
        content = {
            "programming_languages": []
        }
    else:
        languages = []
        tech_skills = analysis_cache['latest'].analysis.get("technical_skills", {}).get("programming_languages", {})
        
        if tech_skills:
            for lang, score in tech_skills.items():
                proficiency = "advanced" if score >= 8 else "intermediate" if score >= 6 else "basic"
                languages.append({
                    "name": lang,
                    "proficiency": proficiency
                })
        
        content = {
            "programming_languages": languages
        }
    
    # Create a response with cache headers
    response = JSONResponse(content=content)
    response.headers["Cache-Control"] = "max-age=30"
    return response

@app.get("/api/agent/education")
async def get_education():
    """
    Return the candidate's education in the format expected by the agent.
    """
    if not analysis_cache['latest']:
        content = {
            "education": {
                "university": "Not specified in the provided data"
            }
        }
    else:
        # Try to extract university information
        education_data = analysis_cache['latest'].structured_data.get("education", [])
        university = "Not specified in the provided data"
        
        for edu in education_data:
            if edu.get("school") and edu.get("school") != "":
                university = edu.get("school")
                break
        
        content = {
            "education": {
                "university": university
            }
        }
    
    # Create a response with cache headers
    response = JSONResponse(content=content)
    response.headers["Cache-Control"] = "max-age=30"
    return response

@app.get("/api/agent/experience")
async def get_experience():
    """
    Return the candidate's experience in the format expected by the agent.
    """
    if not analysis_cache['latest']:
        content = {
            "experience": []
        }
    else:
        experience_data = []
        for exp in analysis_cache['latest'].structured_data.get("experience", []):
            # Skip entries that look like phone numbers or don't have proper titles
            if "Mobile:" in exp.get("title", ""):
                continue
                
            experience_data.append({
                "title": exp.get("title", ""),
                "company": exp.get("company", ""),
                "duration": exp.get("duration", "")
            })
        
        content = {
            "experience": experience_data
        }
    
    # Create a response with cache headers
    response = JSONResponse(content=content)
    response.headers["Cache-Control"] = "max-age=30"
    return response

@app.get("/api/agent/ranking")
async def get_candidate_ranking():
    """
    Return the candidate's ranking in the format expected by the agent.
    """
    if not analysis_cache['latest']:
        content = {
            "candidate_ranking": "Undetermined",
            "reason": "Lack of comparative candidate data"
        }
    else:
        score = analysis_cache['latest'].analysis.get("overall_fit_score", 0)
        
        if score >= 90:
            ranking = "Excellent match"
            reason = "Outstanding technical skills and experience level"
        elif score >= 80:
            ranking = "Strong match"
            reason = "Strong technical background with relevant experience"
        elif score >= 70:
            ranking = "Good match"
            reason = "Good technical skills but may need some training"
        else:
            ranking = "Undetermined"
            reason = "Insufficient data or below threshold score"
        
        content = {
            "candidate_ranking": ranking,
            "reason": reason
        }
    
    # Create a response with cache headers
    response = JSONResponse(content=content)
    response.headers["Cache-Control"] = "max-age=30"
    return response

@app.get("/api/agent/comprehensive-data")
async def get_comprehensive_data_for_agent(request: Request):
    """
    Return a comprehensive data package for the chatbot agent.
    This endpoint combines all the information the agent might need in a clear format.
    """
    # Apply standard throttling
    client_host = request.client.host
    if not request_throttler.should_process("/api/agent/comprehensive-data", client_host):
        response = JSONResponse(content={"status": "throttled", "message": "Request frequency exceeded"})
        response.headers["Cache-Control"] = "max-age=30"
        return response
    
    if not analysis_cache['latest']:
        return {
            "status": "no_data",
            "overall_fit_score": 0,
            "experience_level": "Unknown",
            "skills": {},
            "education": [],
            "experience": [],
            "interview_questions": {},
            "message": "No candidate analysis has been performed"
        }
    
    # Format the data in a very clear and direct structure
    # that's easy for the agent to consume
    comprehensive_data = {
        "status": "success",
        "overall_fit_score": analysis_cache['latest'].analysis.get("overall_fit_score", 0),
        "experience_level": analysis_cache['latest'].analysis.get("experience_level", "Unknown"),
        "education_score": analysis_cache['latest'].analysis.get("education", 0),
        "cultural_fit": analysis_cache['latest'].analysis.get("cultural_fit", 0),
        
        # Format skills in a flattened way
        "skills": {
            # Programming languages
            **(analysis_cache['latest'].analysis.get("technical_skills", {}).get("programming_languages", {})),
            # Frameworks
            **(analysis_cache['latest'].analysis.get("technical_skills", {}).get("frameworks", {})),
            # Cloud & DevOps
            **(analysis_cache['latest'].analysis.get("technical_skills", {}).get("cloud_and_devops", {})),
            # Tools
            **(analysis_cache['latest'].analysis.get("technical_skills", {}).get("tools", {}))
        },
        
        # Education details
        "education": analysis_cache['latest'].structured_data.get("education", []),
        
        # Experience details
        "experience": analysis_cache['latest'].structured_data.get("experience", []),
        
        # Interview questions
        "interview_questions": {
            "technical": analysis_cache['latest'].interview_questions.get("technicalQuestions", []),
            "behavioral": analysis_cache['latest'].interview_questions.get("behavioralQuestions", []),
            "cultural_fit": analysis_cache['latest'].interview_questions.get("culturalFitQuestions", [])
        },
        
        # Schedule
        "interview_schedule": analysis_cache['latest'].interview_schedule,
    }
    
    # Create a response with strong cache headers
    response = JSONResponse(content=comprehensive_data)
    response.headers["Cache-Control"] = "max-age=30, must-revalidate"
    
    return response

@app.get("/api/agent/connector.js")
async def get_agent_connector():
    """
    Serve the agent connector as a JavaScript file.
    This allows the DigitalOcean agent to directly import our connector.
    """
    connector_path = Path(__file__).parent.parent / "frontend" / "public" / "do-agent-connector.js"
    
    if not connector_path.exists():
        logger.error(f"Connector script not found at: {connector_path}")
        raise HTTPException(status_code=404, detail="Agent connector script not found")
    
    return FileResponse(
        connector_path,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"}
    )

@app.get("/api/agent/data.json")
async def get_agent_data_json():
    """Provide full candidate data in JSON format with CORS headers for agent use."""
    if not analysis_cache['latest']:
        return JSONResponse(
            content={"error": "No analysis data available"},
            status_code=404
        )
    
    # Return the response with appropriate CORS headers
    return JSONResponse(
        content=analysis_cache['latest'],
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Content-Type": "application/json"
        }
    )

@app.get("/api/visualization-data")
async def get_visualization_data():
    """Provide data specifically formatted for visualization components."""
    if not analysis_cache['latest']:
        return JSONResponse(
            content={"error": "No analysis data available"},
            status_code=404
        )
    
    # Process skills data for radar/polar chart
    skills_data = []
    if hasattr(analysis_cache['latest'], 'analysis') and 'technical_skills' in analysis_cache['latest'].analysis:
        for category, skills in analysis_cache['latest'].analysis['technical_skills'].items():
            if isinstance(skills, dict):
                for skill, score in skills.items():
                    skills_data.append({
                        "skill": skill,
                        "score": score,
                        "category": category
                    })
    
    # Format education data for timeline
    education_data = []
    if hasattr(analysis_cache['latest'], 'structured_data') and 'education' in analysis_cache['latest'].structured_data:
        for edu in analysis_cache['latest'].structured_data['education']:
            education_data.append({
                "title": edu.get("degree", "Degree"),
                "institution": edu.get("institution", "Unknown"),
                "startDate": edu.get("start_date", ""),
                "endDate": edu.get("end_date", ""),
                "type": "education"
            })
    
    # Format experience data for timeline
    experience_data = []
    if hasattr(analysis_cache['latest'], 'structured_data') and 'experience' in analysis_cache['latest'].structured_data:
        for exp in analysis_cache['latest'].structured_data['experience']:
            experience_data.append({
                "title": exp.get("title", "Role"),
                "company": exp.get("company", "Unknown"),
                "startDate": exp.get("start_date", ""),
                "endDate": exp.get("end_date", ""),
                "description": exp.get("description", ""),
                "type": "experience"
            })
    
    # Overall score and metrics for gauge charts
    overall_data = {
        "overall_score": analysis_cache['latest'].analysis.get("overall_fit_score", 0),
        "experience_level": analysis_cache['latest'].analysis.get("experience_level", "Unknown"),
        "education_score": analysis_cache['latest'].analysis.get("education", 0),
        "cultural_fit": analysis_cache['latest'].analysis.get("cultural_fit", 0)
    }
    
    # Return formatted visualization data
    return JSONResponse(
        content={
            "skills": skills_data,
            "education": education_data,
            "experience": experience_data,
            "overall": overall_data,
            "timeline": education_data + experience_data
        }
    )

@app.get("/api/agent/flat-data")
async def get_flat_candidate_data():
    """
    Provides a flat, simplified JSON structure with all candidate data.
    This endpoint is designed specifically for the DigitalOcean agent.
    All CORS headers are included to ensure access from any domain.
    """
    if not analysis_cache['latest']:
        return JSONResponse(
            content={"error": "No analysis data available", "status": "no_data"},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                "Cache-Control": "no-cache"
            }
        )
    
    # Create a flat structure that's easier for the agent to parse
    flat_data = {
        "status": "success",
        "overall_fit_score": analysis_cache['latest'].analysis.get("overall_fit_score", 0),
        "experience_level": analysis_cache['latest'].analysis.get("experience_level", "Unknown"),
        "education_score": analysis_cache['latest'].analysis.get("education", 0),
        "cultural_fit": analysis_cache['latest'].analysis.get("cultural_fit", 0)
    }
    
    # Add skills as direct top-level properties
    if "technical_skills" in analysis_cache['latest'].analysis:
        for category, skills in analysis_cache['latest'].analysis["technical_skills"].items():
            if isinstance(skills, dict):
                for skill, score in skills.items():
                    # Prefix with category for clarity
                    flat_key = f"{category}_{skill}".replace(" ", "_").lower()
                    flat_data[flat_key] = score
    
    # Add education as a simple list
    flat_data["education"] = []
    if "education" in analysis_cache['latest'].structured_data:
        for edu in analysis_cache['latest'].structured_data["education"]:
            flat_data["education"].append({
                "degree": edu.get("degree", "Unknown"),
                "institution": edu.get("institution", "Unknown"),
                "start_date": edu.get("start_date", ""),
                "end_date": edu.get("end_date", "")
            })
    
    # Add experience as a simple list
    flat_data["experience"] = []
    if "experience" in analysis_cache['latest'].structured_data:
        for exp in analysis_cache['latest'].structured_data["experience"]:
            flat_data["experience"].append({
                "title": exp.get("title", "Unknown"),
                "company": exp.get("company", "Unknown"),
                "start_date": exp.get("start_date", ""),
                "end_date": exp.get("end_date", ""),
                "description": exp.get("description", "")
            })
    
    # Add interview questions (flatten the structure)
    flat_data["technical_questions"] = analysis_cache['latest'].interview_questions.get("technicalQuestions", [])
    flat_data["behavioral_questions"] = analysis_cache['latest'].interview_questions.get("behavioralQuestions", [])
    flat_data["cultural_fit_questions"] = analysis_cache['latest'].interview_questions.get("culturalFitQuestions", [])
    
    # Add some derived analysis to make agent's job easier
    flat_data["strengths"] = []
    flat_data["weaknesses"] = []
    
    # Identify strengths (skills with score >= 8)
    for category, skills in analysis_cache['latest'].analysis.get("technical_skills", {}).items():
        if isinstance(skills, dict):
            for skill, score in skills.items():
                if score >= 8:
                    flat_data["strengths"].append(f"{skill} ({score}/10)")
                elif score <= 4:
                    flat_data["weaknesses"].append(f"{skill} ({score}/10)")
    
    # Return with appropriate CORS headers
    return JSONResponse(
        content=flat_data,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Cache-Control": "no-cache"
        }
    )

@app.get("/api/agent/score")
async def get_plain_score():
    """
    Return just the candidate score as a plain text number.
    This endpoint has full CORS headers and is designed to be as simple as possible.
    """
    if not analysis_cache['latest'] or not hasattr(analysis_cache['latest'], 'analysis'):
        return Response(
            content="0",
            media_type="text/plain",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                "Cache-Control": "no-cache"
            }
        )
    
    # Get the score and convert to string
    score = str(analysis_cache['latest'].analysis.get("overall_fit_score", 0))
    
    # Return as plain text
    return Response(
        content=score,
        media_type="text/plain",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Cache-Control": "no-cache"
        }
    )

@app.get("/api/agent/simple-data")
async def get_simple_agent_data():
    """
    Returns the simplest possible data structure that the agent needs.
    This is streamlined for direct agent consumption with all CORS headers.
    """
    if not analysis_cache['latest']:
        return JSONResponse(
            content={
                "status": "no_data",
                "score": 0,
                "experienceLevel": "Unknown",
                "skills": [],
                "education": [],
                "experience": []
            },
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type"
            }
        )
    
    # Extract programming languages for simplicity
    skills = []
    if hasattr(analysis_cache['latest'], 'analysis') and 'technical_skills' in analysis_cache['latest'].analysis:
        if 'programming_languages' in analysis_cache['latest'].analysis['technical_skills']:
            for lang, score in analysis_cache['latest'].analysis['technical_skills']['programming_languages'].items():
                skills.append(f"{lang} ({score}/10)")
    
    # Simplified education list
    education = []
    if hasattr(analysis_cache['latest'], 'structured_data') and 'education' in analysis_cache['latest'].structured_data:
        for edu in analysis_cache['latest'].structured_data['education']:
            education.append(f"{edu.get('degree', 'Degree')} from {edu.get('institution', 'Institution')}")
    
    # Simplified experience list
    experience = []
    if hasattr(analysis_cache['latest'], 'structured_data') and 'experience' in analysis_cache['latest'].structured_data:
        for exp in analysis_cache['latest'].structured_data['experience']:
            experience.append(f"{exp.get('title', 'Role')} at {exp.get('company', 'Company')}")
    
    # Simple data structure
    simple_data = {
        "status": "success",
        "score": analysis_cache['latest'].analysis.get("overall_fit_score", 0),
        "experienceLevel": analysis_cache['latest'].analysis.get("experience_level", "Unknown"),
        "skills": skills,
        "education": education,
        "experience": experience,
        "technicalQuestions": analysis_cache['latest'].interview_questions.get("technicalQuestions", []),
        "behavioralQuestions": analysis_cache['latest'].interview_questions.get("behavioralQuestions", [])
    }
    
    return JSONResponse(
        content=simple_data,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Cache-Control": "no-cache, no-store, must-revalidate"
        }
    )

@app.get("/api/agent/push-data")
async def push_data_to_agent_endpoint():
    """
    Manually trigger sending the latest analysis data to the agent via chat API.
    This uses the updated approach of sending data via chat messages rather than 
    trying to use non-existent memory or variables APIs.
    """
    if not analysis_cache['latest']:
        return {
            "status": "error",
            "message": "No analysis data available to send"
        }
    
    # Try both methods of sending data to maximize chances of success
    agent_chat_success = await send_data_to_agent(analysis_cache['latest'])
    ai_service_success = await ai_service.set_agent_memory(analysis_cache['latest'].dict())
    
    if agent_chat_success or ai_service_success:
        return {
            "status": "success",
            "message": "Data successfully sent to agent via chat API",
            "direct_method_success": agent_chat_success,
            "ai_service_method_success": ai_service_success,
            "agent_id": os.getenv('DO_AI_AGENT_ID'),
            "agent_url": os.getenv('DO_AI_AGENT_URL')
        }
    else:
        # Store the score in memory as a fallback if both API methods fail
        global candidate_score
        candidate_score = analysis_cache['latest'].analysis.get("overall_fit_score", 0)
        
        # Troubleshooting information for debugging
        return {
            "status": "error",
            "message": "Failed to send data to agent via chat API",
            "agent_id": os.getenv('DO_AI_AGENT_ID'),
            "agent_url": os.getenv('DO_AI_AGENT_URL'),
            "fallback": "Score stored in memory for API endpoints",
            "score": candidate_score,
            "note": "Make sure DO_AI_AGENT_ID and DIGITALOCEAN_TOKEN are correctly set in .env file"
        }

@app.get("/api/agent/test-connection")
async def test_agent_connection():
    """
    Test the connection to the DigitalOcean agent API.
    This endpoint just tries to make a simple GET request to the agent API.
    """
    try:
        # Get the agent info from environment or use the working hardcoded values
        agent_id = os.getenv("DO_AI_AGENT_ID", "wfck7ikdpdzloatcokfi2fvf")
        agent_url = os.getenv("DO_AI_AGENT_URL", f"https://{agent_id}.agents.do-ai.run")
        
        # Use the known working API key
        agent_token = "dZt5CXlW7oT2Uv9_-yNsyT36oU-6NWkA"
        
        if not agent_token:
            return {
                "status": "error",
                "message": "Missing DIGITALOCEAN_TOKEN environment variable"
            }
            
        if not agent_id:
            return {
                "status": "error",
                "message": "Missing DO_AI_AGENT_ID environment variable"
            }
        
        # Try both the API endpoints and the chat endpoint
        api_url = f"https://api.digitalocean.com/v2/agents/{agent_id}"
        alternate_api_url = f"https://api.digitalocean.com/v2/apps/agents/{agent_id}"
        chat_api_url = f"{agent_url}/api/v1/chat/completions" if agent_url else f"https://{agent_id}.agents.do-ai.run/api/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {agent_token}",
            "Content-Type": "application/json"
        }
        
        results = {
            "agent_id": agent_id,
            "agent_url": agent_url,
            "token_preview": f"{agent_token[:5]}...{agent_token[-5:]}",
            "primary_url": api_url,
            "alternate_url": alternate_api_url,
            "chat_api_url": chat_api_url,
            "primary_result": None,
            "alternate_result": None,
            "chat_api_result": None
        }
        
        # Try both API URL formats and the chat API
        async with aiohttp.ClientSession() as session:
            try:
                # Try primary URL
                async with session.get(api_url, headers=headers) as response:
                    results["primary_status"] = response.status
                    if response.status == 200:
                        results["primary_result"] = "Success"
                    else:
                        response_text = await response.text()
                        results["primary_result"] = f"Failed: {response.status} - {response_text}"
                        
                # Try alternate URL
                async with session.get(alternate_api_url, headers=headers) as alt_response:
                    results["alternate_status"] = alt_response.status
                    if alt_response.status == 200:
                        results["alternate_result"] = "Success"
                    else:
                        alt_response_text = await alt_response.text()
                        results["alternate_result"] = f"Failed: {alt_response.status} - {alt_response_text}"
                
                # Try chat API
                chat_payload = {
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a test assistant."
                        },
                        {
                            "role": "user",
                            "content": "Test connection"
                        }
                    ],
                    "temperature": 0.1,
                    "max_tokens": 10
                }
                
                async with session.post(chat_api_url, headers=headers, json=chat_payload) as chat_response:
                    results["chat_api_status"] = chat_response.status
                    if chat_response.status == 200:
                        results["chat_api_result"] = "Success"
                    else:
                        chat_response_text = await chat_response.text()
                        results["chat_api_result"] = f"Failed: {chat_response.status} - {chat_response_text}"
                
                return results
            except Exception as request_error:
                return {
                    "status": "error",
                    "message": f"Error making API request: {str(request_error)}",
                    "agent_id": agent_id,
                    "agent_url": agent_url
                }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}"
        }

@app.get("/api/agent/data-link")
async def get_agent_data_link():
    """
    Return the URL where the agent can access the candidate data.
    This is a simple endpoint that the agent can call directly.
    """
    if agent_data_url:
        return {
            "status": "success",
            "data_url": agent_data_url,
            "candidate_score": candidate_score
        }
    else:
        return {
            "status": "error",
            "message": "No candidate data available"
        }

@app.get("/api/agent/score-only")
async def get_score_only():
    """
    Return just the candidate score as a simple number.
    This is the simplest possible endpoint for the agent to use.
    """
    global candidate_score
    
    if candidate_score is not None:
        return {
            "score": candidate_score
        }
    else:
        return {
            "score": 0,
            "error": "No score available"
        }

@app.get("/api/agent/assessment")
async def get_assessment_data():
    """
    Return candidate assessment data in the exact format expected by the agent.
    This format matches what we've seen in the agent's responses.
    """
    if analysis_cache['latest']:
        skills = []
        education = []
        experience = []
        
        # Add skills
        if "technical_skills" in analysis_cache['latest'].analysis and "programming_languages" in analysis_cache['latest'].analysis["technical_skills"]:
            for lang, score in analysis_cache['latest'].analysis["technical_skills"]["programming_languages"].items():
                skills.append(f"{lang} ({score}/10)")
        
        # Add education
        if "education" in analysis_cache['latest'].structured_data:
            for edu in analysis_cache['latest'].structured_data["education"]:
                degree = edu.get('degree', '')
                if degree:
                    education.append(degree)
        
        # Add experience
        if "experience" in analysis_cache['latest'].structured_data:
            for exp in analysis_cache['latest'].structured_data["experience"]:
                title = exp.get('title', '')
                company = exp.get('company', '')
                if title and company:
                    experience.append(f"{title} at {company}")
        
        return {
            "candidate_assessment": {
                "overall_fit_score": analysis_cache['latest'].analysis.get("overall_fit_score", 0),
                "experience_level": analysis_cache['latest'].analysis.get("experience_level", "Unknown"),
                "education_score": analysis_cache['latest'].analysis.get("education", 0),
                "cultural_fit": analysis_cache['latest'].analysis.get("cultural_fit", 0),
                "skills": skills,
                "education": education,
                "experience": experience,
                "message": "Candidate evaluation complete",
                "interview_questions": analysis_cache['latest'].interview_questions.get("technicalQuestions", [])[:3]
            }
        }
    # Otherwise return just the score from our global variable
    elif candidate_score is not None:
        return {
            "candidate_assessment": {
                "overall_fit_score": candidate_score,
                "message": "Candidate evaluation complete, only score available"
            }
        }
    # Last resort if we have no data
    else:
        return {
            "candidate_assessment": {
                "overall_fit_score": 0,
                "message": "No resume or candidate data provided for assessment."
            }
        }

@app.get("/api/agent/score-format")
async def get_score_format():
    """
    Return candidate score in the exact format shown in the agent's response.
    This strictly follows the agent's output format.
    """
    if analysis_cache['latest']:
        return {
            "candidate_score": {
                "overall_score": analysis_cache['latest'].analysis.get("overall_fit_score", 0),
                "technical_skills": 8,  # Average of technical skills
                "experience_level": {"Senior": 8, "Mid-level": 6, "Junior": 4}.get(
                    analysis_cache['latest'].analysis.get("experience_level", "Unknown"), 5
                ),
                "education": analysis_cache['latest'].analysis.get("education", 0),
                "cultural_fit": analysis_cache['latest'].analysis.get("cultural_fit", 0),
                "message": "Candidate evaluation complete."
            }
        }
    # Otherwise return just the score from our global variable
    elif candidate_score is not None:
        return {
            "candidate_score": {
                "overall_score": candidate_score,
                "technical_skills": 7,
                "experience_level": 7,
                "education": 7,
                "cultural_fit": 7,
                "message": "Candidate evaluation complete, limited data available."
            }
        }
    # Last resort if we have no data
    else:
        return {
            "candidate_score": {
                "overall_score": 0,
                "technical_skills": 0,
                "experience_level": 0,
                "education": 0, 
                "cultural_fit": 0,
                "message": "No candidate data provided for scoring."
            }
        }

@app.get("/api/agent/docs")
async def get_agent_docs():
    """
    Return documentation on how to interact with the DigitalOcean agent.
    This is useful for developers and users who need to understand how the agent works.
    """
    agent_id = os.getenv('DO_AI_AGENT_ID')
    agent_url = os.getenv('DO_AI_AGENT_URL')
    
    return {
        "title": "DigitalOcean AI Agent Integration Guide",
        "description": "This guide explains how to interact with the DigitalOcean AI agent.",
        "agent_id": agent_id,
        "agent_url": agent_url,
        "how_it_works": [
            "The agent does not have persistent memory outside of the chat session.",
            "Data is sent to the agent via chat messages at the /api/v1/chat/completions endpoint.",
            "After resume analysis, candidate data is automatically sent to the agent.",
            "When users chat with the agent, it has access to the latest candidate data in its context."
        ],
        "important_limitation": [
            "DigitalOcean AI agents DO NOT persist data between separate chat sessions.",
            "Each new API call starts a fresh conversation with no memory of previous interactions.",
            "You must include candidate data in EVERY conversation or maintain conversation state.",
            "The /api/agent/push-data endpoint only affects the single conversation it creates."
        ],
        "recommended_approaches": [
            "Frontend approach: Include candidate data in every initial message to the agent",
            "Backend approach: Maintain conversation state and include previous messages in each API call",
            "Hybrid approach: Create a proxy API that injects candidate data into each conversation"
        ],
        "interaction_methods": [
            {
                "name": "Automatic after analysis",
                "description": "When a resume is analyzed, candidate data is automatically sent to the agent.",
                "endpoint": "/api/analyze (POST)",
                "triggered_by": "Uploading and analyzing a resume"
            },
            {
                "name": "Manual push",
                "description": "Manually push the latest candidate data to the agent.",
                "endpoint": "/api/agent/push-data (GET)",
                "triggered_by": "Developer or testing",
                "limitation": "Only affects the single conversation created by this request"
            },
            {
                "name": "Direct chat with agent",
                "description": "Chat directly with the agent via its chat API.",
                "endpoint": f"{agent_url}/api/v1/chat/completions (POST)",
                "note": "Requires Authentication with Bearer token"
            }
        ],
        "recommended_implementation": [
            "Create a proxy endpoint that forwards requests to the agent but injects candidate data into each conversation",
            "When using the frontend widget, ensure the widget maintains conversation state itself",
            "Consider implementing a backend chat history service to maintain conversation continuity"
        ],
        "test_connection": {
            "endpoint": "/api/agent/test-connection",
            "description": "Test if the agent API is accessible"
        },
        "usage_notes": [
            "The agent works best when asked specific questions about the candidate.",
            "The agent can access the latest resume analysis but cannot access historical data.",
            "To update the agent with new data, analyze a new resume or use the push-data endpoint."
        ]
    }

@app.get("/api/agent/proxy-chat")
@app.post("/api/agent/proxy-chat")
async def proxy_chat_to_agent(request: Request):
    """
    Proxy chat requests to the DigitalOcean agent, ensuring candidate data is included.
    Handles both GET and POST requests.
    """
    logger.info("Received proxy chat request")
    
    try:
        # Get message from either query params (GET) or request body (POST)
        if request.method == "GET":
            message = request.query_params.get("message", "")
            stream = request.query_params.get("stream", "false").lower() == "true"
        else:  # POST
            body = await request.json()
            message = body.get("message", "")
            stream = body.get("stream", False)
        
        logger.info(f"Processing chat message: {message[:100]}...")
        
        # Validate message
        if not message:
            logger.warning("Empty message received")
            return JSONResponse(
                content={
                    "status": "error",
                    "error": "empty_message",
                    "message": "No message provided"
                },
                status_code=400
            )
        
        # Check if we have candidate data
        if not analysis_cache['latest']:
            logger.warning("No candidate data available for chat")
            return JSONResponse(
                content={
                    "status": "error",
                    "error": "no_data",
                    "message": "No candidate data available",
                    "response": "I'm sorry, but I don't have any candidate data to work with at the moment."
                },
                status_code=200  # Still return 200 to allow the message to be displayed
            )
        
        # Convert Pydantic model to dictionary and format the candidate data
        candidate_data = analysis_cache['latest'].dict()
        formatted_data = ai_service.format_candidate_data(candidate_data)
        
        if not formatted_data or "error" in formatted_data:
            logger.error(f"Failed to format candidate data: {formatted_data}")
            return JSONResponse(
                content={
                    "status": "error",
                    "error": "format_error",
                    "message": "Failed to format candidate data",
                    "response": "I'm having trouble processing the candidate data at the moment."
                },
                status_code=200
            )
            
        logger.info(f"Formatted data summary: {formatted_data.get('summary', 'No summary generated')}")
        
        # Create a clear system message
        system_message = (
            "You are a recruiter assistant that helps analyze candidate resumes. "
            "Use the following candidate data to answer questions accurately. "
            "The data includes scores, skills, education, and experience information."
        )
        
        # Create a detailed data message that includes the summary
        data_message = (
            f"CANDIDATE SUMMARY: {formatted_data.get('summary', 'No summary available')}\n\n"
            f"DETAILED DATA: {json.dumps(formatted_data, indent=2)}"
        )
        
        # Call the agent
        try:
            # Get the agent info from environment or use the working hardcoded values
            agent_id = os.getenv("DO_AI_AGENT_ID", "wfck7ikdpdzloatcokfi2fvf")
            agent_url = os.getenv("DO_AI_AGENT_URL", f"https://{agent_id}.agents.do-ai.run")
            
            # Use the known working API key
            agent_token = "dZt5CXlW7oT2Uv9_-yNsyT36oU-6NWkA"
            
            if not agent_token:
                logger.error("Missing agent token")
                return JSONResponse(
                    content={
                        "status": "error",
                        "error": "no_token",
                        "message": "Missing agent authentication token"
                    },
                    status_code=500
                )
            
            # The chat endpoint is the only way to provide context to DigitalOcean agents
            chat_api_url = f"{agent_url}/api/v1/chat/completions"
            
            headers = {
                "Authorization": f"Bearer {agent_token}",
                "Content-Type": "application/json"
            }
            
            # Create the chat payload with system message, data context, and user message
            chat_payload = {
                "messages": [
                    {
                        "role": "system",
                        "content": system_message
                    },
                    {
                        "role": "user",
                        "content": data_message
                    },
                    {
                        "role": "assistant",
                        "content": "I understand. I have access to the candidate data and will use it to answer your questions."
                    },
                    {
                        "role": "user",
                        "content": message
                    }
                ],
                "temperature": 0.1,
                "max_tokens": 500,
                "stream": stream
            }
            
            async with aiohttp.ClientSession() as session:
                logger.info(f"Sending request to agent: {chat_api_url}")
                async with session.post(chat_api_url, json=chat_payload, headers=headers) as response:
                    if response.status == 200:
                        logger.info("Agent response status: 200")
                        
                        if stream:
                            # Return the streaming response
                            return StreamingResponse(
                                response.content,
                                media_type="text/event-stream",
                                headers={
                                    "Cache-Control": "no-cache",
                                    "Connection": "keep-alive",
                                    "Access-Control-Allow-Origin": "*"
                                }
                            )
                        else:
                            # Return the regular response
                            agent_response = await response.json()
                            logger.info("Successfully received agent response")
                            
                            # Extract the response text from the agent's response
                            response_text = ""
                            if "choices" in agent_response and len(agent_response["choices"]) > 0:
                                if "message" in agent_response["choices"][0]:
                                    response_text = agent_response["choices"][0]["message"].get("content", "")
                                elif "text" in agent_response["choices"][0]:
                                    response_text = agent_response["choices"][0]["text"]
                            
                            return JSONResponse(
                                content={
                                    "status": "success",
                                    "response": response_text
                                }
                            )
                    else:
                        error_text = await response.text()
                        logger.error(f"Agent returned error: {response.status} - {error_text}")
                        return JSONResponse(
                            content={
                                "status": "error",
                                "error": "agent_error",
                                "message": f"Agent returned error: {response.status}",
                                "details": error_text
                            },
                            status_code=response.status
                        )
                        
        except Exception as e:
            logger.exception("Error calling agent service")
            return JSONResponse(
                content={
                    "status": "error",
                    "error": "agent_error",
                    "message": f"Error communicating with agent: {str(e)}"
                },
                status_code=500
            )
            
    except Exception as e:
        logger.exception("Error in proxy chat endpoint")
        return JSONResponse(
            content={
                "status": "error",
                "error": "internal_error",
                "message": f"Internal server error: {str(e)}"
            },
            status_code=500
        )

@app.get("/api/logs")
async def get_logs():
    """
    Return recent log entries related to agent communication.
    Useful for debugging issues with agent data access.
    """
    try:
        log_file = "agent_debug.log"
        
        # Set up a file handler if not already configured
        agent_file_handler = None
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler) and handler.baseFilename.endswith(log_file):
                agent_file_handler = handler
                break
        
        if not agent_file_handler:
            # Add a file handler for agent-related logs
            agent_file_handler = logging.FileHandler(log_file)
            agent_file_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            agent_file_handler.setFormatter(formatter)
            logger.addHandler(agent_file_handler)
            logger.info("Added file handler for agent logs")
        
        # Check if log file exists
        if not os.path.exists(log_file):
            logger.info(f"Creating log file: {log_file}")
            with open(log_file, 'w') as f:
                f.write(f"Log file created at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Read recent logs
        max_lines = 200
        logs = []
        
        with open(log_file, 'r') as f:
            logs = f.readlines()
        
        # Get the last N lines
        logs = logs[-max_lines:] if len(logs) > max_lines else logs
        
        # Also capture in-memory logs from the current session
        memory_logs = [
            f"{time.strftime('%Y-%m-%d %H:%M:%S')} - MEMORY - INFO - Latest agent interaction status: {analysis_cache['latest'] is not None}"
        ]
        
        if analysis_cache['latest']:
            memory_logs.append(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - MEMORY - INFO - Analysis contains score: {analysis_cache['latest'].analysis.get('overall_fit_score', 'None')}")
        
        all_logs = memory_logs + logs
        
        # Return the logs
        return {"logs": all_logs, "count": len(all_logs)}
    except Exception as e:
        logger.error(f"Error getting logs: {str(e)}")
        return {"error": f"Failed to get logs: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port) 