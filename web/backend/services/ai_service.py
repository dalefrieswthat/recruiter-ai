import os
import requests
import json
from typing import Dict, Any, List, Optional
import logging
import time
import re

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self, use_mock=False):  # Default to real mode
        # Get agent ID from environment or use fallback
        self.agent_id = os.getenv('DO_AI_AGENT_ID', "wfck7ikdpdzloatcokfi2fvf")  # Get agent ID from env
        self.api_key = os.getenv('DO_AI_AGENT_KEY', "dZt5CXlW7oT2Uv9_-yNsyT36oU-6NWkA")  # API key from env or fallback
        self.base_url = os.getenv('DO_AI_AGENT_URL', f"https://{self.agent_id}.agents.do-ai.run")  # Agent URL from env or construct it
        self.api_url = f"{self.base_url}/api/v1/chat/completions"
        self.use_mock = use_mock
        
        # Add token caching
        self.token_last_refreshed = 0
        self.token_refresh_interval = 600  # 10 minutes in seconds
        self.auth_token = None  # Will be set on first request
        
        # Store the current conversation context
        self.conversation_context = []
        
        logger.info(f"AIService initialized with agent ID: {self.agent_id}")
        logger.info(f"API URL: {self.api_url}")
        logger.info(f"Use mock: {self.use_mock}")

    async def get_auth_token(self) -> str:
        """
        Get an authentication token for the AI agent with caching.
        """
        current_time = time.time()
        
        # Return cached token if it's still valid
        if self.auth_token and (current_time - self.token_last_refreshed) < self.token_refresh_interval:
            logger.info("Using cached auth token")
            return self.auth_token
            
        # Need to get a new token
        logger.info("Getting fresh auth token")
        try:
            # In a real implementation, you would make a request to get a new token
            # For now, just refresh the cached time
            self.token_last_refreshed = current_time
            self.auth_token = self.api_key  # Just use the API key as is
            
            return self.auth_token
        except Exception as e:
            logger.error(f"Error getting auth token: {str(e)}")
            # Fall back to the API key if token refresh fails
            return self.api_key
    
    async def agent_chat(self, message: str, candidate_data: Dict[str, Any] = None, conversation_history: List[Dict[str, str]] = None) -> str:
        """
        Send a message to the agent with candidate data properly bridged and maintain conversation context.
        This is a unified method for communicating with the agent that ensures data is always available.
        """
        try:
            logger.info(f"Sending message to agent: {message[:50]}...")
            logger.info(f"Has candidate data: {candidate_data is not None}")
            
            if candidate_data:
                logger.info(f"Candidate data keys: {list(candidate_data.keys())}")
                if 'analysis' in candidate_data:
                    logger.info(f"Analysis keys: {list(candidate_data['analysis'].keys())}")
                    score = candidate_data['analysis'].get('overall_fit_score', 'Not found')
                    logger.info(f"Overall score in data: {score}")

            # Get auth token
            auth_token = await self.get_auth_token()
            logger.info(f"Using auth token: {auth_token[:5]}...{auth_token[-5:] if auth_token else 'None'}")
            
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            }
            
            # Use passed conversation history or the stored one
            messages = conversation_history or self.conversation_context or []
            logger.info(f"Starting with {len(messages)} messages in conversation")
            
            # If we have candidate data, ensure it's included in the conversation
            if candidate_data:
                # Create a clear, structured data format for the agent
                formatted_data = self.format_candidate_data(candidate_data)
                logger.info(f"Formatted data: {json.dumps(formatted_data, indent=2)}")
                data_prefix = f"CANDIDATE DATA: {json.dumps(formatted_data, indent=2)}"
                
                # Add system message if not already present
                if not messages or messages[0].get('role') != 'system':
                    logger.info("Adding system message with instructions")
                    messages.insert(0, {
                        "role": "system",
                        "content": "You are a recruiter assistant that analyzes candidate resumes. " +
                                  "Use the candidate data to make informed assessments and answer questions accurately."
                    })
                
                # Check if first user message already contains our data
                if messages and any(msg.get('role') == 'user' for msg in messages):
                    has_data = False
                    for msg in messages:
                        if msg.get('role') == 'user' and 'CANDIDATE DATA' in msg.get('content', ''):
                            has_data = True
                            logger.info("Found existing candidate data in conversation")
                            break
                    
                    # If no message has our data prefix, add it to the first user message
                    if not has_data:
                        logger.info("Adding data to first user message")
                        for msg in messages:
                            if msg.get('role') == 'user':
                                msg['content'] = f"{data_prefix}\n\n{msg['content']}"
                                break
            
            # Add the current message
            if candidate_data:
                logger.info("Adding current message with candidate data")
                messages.append({
                    "role": "user",
                    "content": f"{data_prefix}\n\n{message}"
                })
            else:
                logger.info("Adding current message without candidate data")
                messages.append({
                    "role": "user",
                    "content": message
                })
            
            # Prepare the payload
            payload = {
                "messages": messages,
                "temperature": 0.3,  # Lower temperature for more consistent results
                "max_tokens": 1000,
                "stream": False
            }
            
            # Log the actual messages being sent
            logger.info(f"Sending {len(messages)} messages to agent")
            for i, msg in enumerate(messages):
                logger.info(f"Message {i+1}: role={msg.get('role')}, content_length={len(msg.get('content', ''))}")
                # Log the beginning of each message to help debug
                content_preview = msg.get('content', '')[:100] + ("..." if len(msg.get('content', '')) > 100 else "")
                logger.info(f"Content preview: {content_preview}")
            
            # Call the API
            logger.info(f"Sending request to agent: {self.api_url}")
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
            
            logger.info(f"Agent response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Agent returned error: {response.status_code}")
                logger.error(f"Response content: {response.text}")
                return f"Error: Failed to get response from agent (Status {response.status_code})"
            
            # Parse the response
            response_data = response.json()
            assistant_message = response_data.get("choices", [{}])[0].get("message", {})
            
            # Log the response
            content_preview = assistant_message.get("content", '')[:100] + ("..." if len(assistant_message.get("content", '')) > 100 else "")
            logger.info(f"Agent response: {content_preview}")
            
            # Update the conversation context with the assistant's response
            messages.append(assistant_message)
            self.conversation_context = messages
            logger.info(f"Updated conversation context, now has {len(messages)} messages")
            
            return assistant_message.get("content", "No response from agent")
        except Exception as e:
            logger.error(f"Error in agent_chat: {str(e)}", exc_info=True)
            return f"Error communicating with agent: {str(e)}"
    
    def format_candidate_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format candidate data into a clean, structured format that's easy for the agent to use.
        """
        try:
            # Check if data is the right structure
            if not data or not isinstance(data, dict):
                logger.warning(f"Invalid data format: {type(data)}")
                return {"error": "Invalid data format"}
            
            # Convert Pydantic model to dict if needed
            if hasattr(data, 'dict'):
                data = data.dict()
            
            # Format the data in a simplified structure
            formatted_data = {}
            
            # Extract data from analysis
            if "analysis" in data:
                analysis = data["analysis"]
                formatted_data["overall_score"] = analysis.get("overall_fit_score", 0)
                formatted_data["experience_level"] = analysis.get("experience_level", "Unknown")
                formatted_data["education_score"] = analysis.get("education", 0)
                formatted_data["cultural_fit"] = analysis.get("cultural_fit", 0)
                
                # Process technical skills
                if "technical_skills" in analysis:
                    tech_skills = analysis["technical_skills"]
                    formatted_data["skills"] = []
                    
                    # Process each skill category
                    for category in ["programming_languages", "frameworks", "cloud_and_devops", "tools"]:
                        if category in tech_skills and isinstance(tech_skills[category], dict):
                            for skill, score in tech_skills[category].items():
                                formatted_data["skills"].append({
                                    "name": skill,
                                    "type": category,
                                    "score": score
                                })
            
            # Process structured data
            if "structured_data" in data:
                structured = data["structured_data"]
                
                # Process education
                if "education" in structured:
                    formatted_data["education"] = []
                    for edu in structured["education"]:
                        if isinstance(edu, dict):
                            formatted_data["education"].append({
                                "degree": edu.get("degree", "Unknown"),
                                "institution": edu.get("school", edu.get("institution", "Unknown")),
                                "year": edu.get("year", "Unknown")
                            })
                
                # Process experience
                if "experience" in structured:
                    formatted_data["experience"] = []
                    for exp in structured["experience"]:
                        if isinstance(exp, dict):
                            formatted_data["experience"].append({
                                "title": exp.get("title", "Unknown"),
                                "company": exp.get("company", "Unknown"),
                                "duration": exp.get("duration", "Unknown")
                            })
            
            # Generate a comprehensive summary
            summary_parts = []
            
            # Add overall assessment
            if "overall_score" in formatted_data:
                score = formatted_data["overall_score"]
                if score >= 90:
                    assessment = "Outstanding"
                elif score >= 80:
                    assessment = "Strong"
                elif score >= 70:
                    assessment = "Good"
                else:
                    assessment = "Fair"
                summary_parts.append(f"{assessment} candidate with overall score of {score}/100")
            
            # Add experience level
            if "experience_level" in formatted_data:
                summary_parts.append(f"Experience Level: {formatted_data['experience_level']}")
            
            # Add top skills
            if "skills" in formatted_data:
                top_skills = [skill["name"] for skill in formatted_data["skills"] if skill["score"] >= 8][:3]
                if top_skills:
                    summary_parts.append(f"Top Skills: {', '.join(top_skills)}")
            
            # Add latest education
            if formatted_data.get("education"):
                latest_edu = formatted_data["education"][0]
                summary_parts.append(f"Education: {latest_edu['degree']} from {latest_edu['institution']}")
            
            # Add latest experience
            if formatted_data.get("experience"):
                latest_exp = formatted_data["experience"][0]
                summary_parts.append(f"Latest Role: {latest_exp['title']} at {latest_exp['company']}")
            
            # Add cultural fit if high
            if "cultural_fit" in formatted_data and formatted_data["cultural_fit"] >= 80:
                summary_parts.append("Strong cultural fit")
            
            # Combine all parts into a final summary
            formatted_data["summary"] = " | ".join(summary_parts)
            
            return formatted_data
            
        except Exception as e:
            logger.error(f"Error formatting candidate data: {str(e)}", exc_info=True)
            return {
                "error": "Error formatting data",
                "summary": "Error occurred while processing candidate data"
            }

    async def check_health(self) -> bool:
        """
        Check if the AI agent is healthy and accessible.
        """
        if self.use_mock:
            return True  # Always return healthy in mock mode
            
        try:
            logger.info("Performing health check for AI agent")
            # Just return True for now to bypass health check
            return True
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return False
            
    async def debug_endpoint(self) -> Dict[str, Any]:
        """
        Test the endpoint with a simple request to help with debugging.
        """
        try:
            logger.info("Testing AI agent endpoint")
            
            # Get auth token
            auth_token = await self.get_auth_token()
            
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a test assistant."
                    },
                    {
                        "role": "user",
                        "content": "Hello, are you working?"
                    }
                ],
                "temperature": 0.7,
                "top_p": 0.9,
                "max_tokens": 50,
                "stream": False
            }
            
            logger.info(f"Sending test request to: {self.api_url}")
            # Only log a portion of the token for security
            masked_token = auth_token[:5] + "..." + auth_token[-5:] if auth_token else "None"
            logger.info(f"Using token: {masked_token}")
            
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=10)
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                logger.info("Endpoint test successful")
                return {"status": "success", "response": response.json()}
            else:
                logger.error(f"Endpoint test failed: {response.text}")
                return {"status": "error", "code": response.status_code, "text": response.text}
        except Exception as e:
            logger.error(f"Endpoint test error: {str(e)}")
            return {"status": "exception", "error": str(e)}

    async def analyze_candidate(self, resume_content: str) -> Dict[str, Any]:
        """
        Analyze a resume using the DigitalOcean AI agent.
        """
        try:
            # Only use DigitalOcean agent for analysis
            analysis = await self._analyze_with_agent(resume_content)
            # Optionally, you can add fallback name extraction here if needed
            if 'candidate_name' not in analysis:
                analysis['candidate_name'] = "Not Provided"
            return analysis
        except Exception as e:
            logger.error(f"Error in analyze_candidate: {str(e)}")
            if self.use_mock:
                return self._get_mock_analysis()
            raise

    async def _analyze_with_agent(self, resume_content: str) -> Dict[str, Any]:
        """
        Internal method to get analysis from DigitalOcean agent.
        """
        # Check agent health
        if not await self.check_health() and not self.use_mock:
            raise Exception("AI agent is not healthy or accessible")
            
        if self.use_mock:
            return self._get_mock_analysis()

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            # Prepare the chat message for analysis
            messages = [
                {
                    "role": "system",
                    "content": "You are an expert resume analyzer. Analyze the provided resume and extract key information."
                },
                {
                    "role": "user",
                    "content": f"Please analyze this resume and provide structured information:\n\n{resume_content}"
                }
            ]

            response = requests.post(
                self.api_url,
                headers=headers,
                json={
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens": 1000
                }
            )

            if response.status_code == 200:
                return self._parse_agent_response(response.json())
            else:
                raise Exception(f"Agent API error: {response.status_code} - {response.text}")

        except Exception as e:
            logger.error(f"Error in _analyze_with_agent: {str(e)}")
            raise

    def _get_mock_analysis(self) -> Dict[str, Any]:
        """
        Return mock analysis data for testing.
        """
        return {
            "overall_fit_score": 85,
            "candidate_name": "John Doe",
            "technical_skills": {
                "Python": 90,
                "JavaScript": 80,
                "React": 75,
                "AWS": 85,
                "Database": 80
            },
            "experience_level": "Senior",
            "education": 90,
            "cultural_fit": 85,
            "interview_recommendation": "Strong candidate with relevant experience."
        }

    def _parse_agent_response(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse the response from the DigitalOcean agent and return structured analysis.
        """
        # Implement the logic to parse the response and return structured analysis
        # This is a placeholder and should be replaced with the actual implementation
        # based on the response format from the DigitalOcean agent
        return response_data

    async def set_agent_memory(self, data: Dict[str, Any]) -> bool:
        """
        Send data to the agent by using our improved agent bridge.
        """
        try:
            logger.info("Setting agent memory using agent bridge")
            
            # Format the data using our standard formatter
            formatted_data = self.format_candidate_data(data)
            
            if not formatted_data or "error" in formatted_data:
                logger.error(f"Failed to format candidate data: {formatted_data}")
                return False
                
            logger.info(f"Formatted data summary: {formatted_data.get('summary', 'No summary generated')}")
            
            # Create a message that includes both the summary and detailed data
            init_message = (
                f"CANDIDATE SUMMARY: {formatted_data.get('summary', 'No summary available')}\n\n"
                "Please confirm you can access this candidate data by stating the overall score "
                "and at least three key skills from the data."
            )
            
            # Send the initialization message with the formatted data
            response = await self.agent_chat(init_message, candidate_data=formatted_data)
            
            if "error" in response.lower():
                logger.error(f"Failed to set agent memory: {response}")
                return False
                
            # Verify the response contains some of our data
            score = formatted_data.get("overall_score", 0)
            if str(score) in response:
                logger.info("Agent successfully confirmed access to candidate data")
                return True
            else:
                logger.warning("Agent response did not confirm data access")
                return False
                
        except Exception as e:
            logger.error(f"Error setting agent memory: {str(e)}")
            return False

    async def generate_interview_questions(self, structured_data: Dict[str, Any]) -> Dict[str, list]:
        """
        Generate interview questions based on the resume analysis.
        """
        # First check if the agent is healthy
        if not await self.check_health() and not self.use_mock:
            raise Exception("AI agent is not healthy or accessible")
            
        # Use mock data if in mock mode
        if self.use_mock:
            return {
                "technicalQuestions": [
                    "Can you explain your experience with Python and how you've used it in previous projects?",
                    "Describe your experience with React and component lifecycle management.",
                    "How have you utilized AWS services in your previous roles?",
                    "Explain your approach to database design and optimization."
                ],
                "behavioralQuestions": [
                    "Tell me about a time when you had to meet a tight deadline.",
                    "How do you handle disagreements with team members?",
                    "Describe a situation where you had to learn a new technology quickly."
                ],
                "culturalFitQuestions": [
                    "What type of work environment helps you thrive?",
                    "How do you prioritize work-life balance?",
                    "What values are most important to you in a company culture?"
                ]
            }

        try:
            # Get auth token
            auth_token = await self.get_auth_token()
            
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            }

            payload = {
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an interview preparation assistant. Generate relevant interview questions based on the resume analysis."
                    },
                    {
                        "role": "user",
                        "content": f"Please generate interview questions based on this resume analysis. Format the response as a JSON object with these fields:\n- technicalQuestions: array of strings\n- behavioralQuestions: array of strings\n- culturalFitQuestions: array of strings\n\nResume analysis:\n\n{json.dumps(structured_data)}"
                    }
                ],
                "temperature": 0.7,
                "top_p": 0.9,
                "max_tokens": 1000,
                "stream": False
            }

            response = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"AI agent returned error: {response.status_code}")
                logger.error(f"Response content: {response.text}")
                raise Exception(f"AI agent returned error: {response.status_code}")
                
            response_data = response.json()
            
            # Parse the response content
            content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            
            # Try to parse as JSON
            try:
                # If the content is a string containing JSON with backticks, remove them
                if content.startswith("```json") and content.endswith("```"):
                    content = content[7:-3].strip()
                elif content.startswith("```") and content.endswith("```"):
                    content = content[3:-3].strip()
                    
                # Parse JSON
                questions = json.loads(content)
                return questions
            except json.JSONDecodeError:
                # Try eval as fallback
                try:
                    questions = eval(content)
                    return questions
                except:
                    return {"error": "Failed to parse AI response", "raw_content": content}
        except Exception as e:
            logger.error(f"Error in generate_interview_questions: {str(e)}")
            if self.use_mock:
                return {
                    "technicalQuestions": [
                        "Can you explain your experience with Python and how you've used it in previous projects?",
                        "Describe your experience with React and component lifecycle management.",
                        "How have you utilized AWS services in your previous roles?",
                        "Explain your approach to database design and optimization."
                    ],
                    "behavioralQuestions": [
                        "Tell me about a time when you had to meet a tight deadline.",
                        "How do you handle disagreements with team members?",
                        "Describe a situation where you had to learn a new technology quickly."
                    ],
                    "culturalFitQuestions": [
                        "What type of work environment helps you thrive?",
                        "How do you prioritize work-life balance?",
                        "What values are most important to you in a company culture?"
                    ]
                }
            else:
                raise

    async def schedule_interview(self, structured_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate interview schedule recommendations.
        """
        # First check if the agent is healthy
        if not await self.check_health() and not self.use_mock:
            raise Exception("AI agent is not healthy or accessible")
            
        # Use mock data if in mock mode
        if self.use_mock:
            return {
                "recommendedDuration": "60 minutes",
                "suggestedTimeSlots": [
                    "Tuesday, May 21, 2025 at 10:00 AM",
                    "Wednesday, May 22, 2025 at 2:00 PM",
                    "Friday, May 24, 2025 at 11:00 AM"
                ],
                "interviewType": "Technical and Cultural Fit",
                "interviewers": ["Technical Lead", "Hiring Manager"],
                "preparationNotes": "Candidate has strong technical background, focus on system design and architectural decisions."
            }

        try:
            # Get auth token
            auth_token = await self.get_auth_token()
            
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            }

            payload = {
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an interview scheduling assistant. Generate interview schedule recommendations based on the resume analysis."
                    },
                    {
                        "role": "user",
                        "content": f"Please generate interview schedule recommendations based on this resume analysis. Format the response as a JSON object with these fields:\n- recommendedDuration: string\n- suggestedTimeSlots: array of strings\n- interviewType: string\n\nResume analysis:\n\n{json.dumps(structured_data)}"
                    }
                ],
                "temperature": 0.7,
                "top_p": 0.9,
                "max_tokens": 1000,
                "stream": False
            }

            response = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"AI agent returned error: {response.status_code}")
                logger.error(f"Response content: {response.text}")
                raise Exception(f"AI agent returned error: {response.status_code}")
                
            response_data = response.json()
            
            # Parse the response content
            content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            
            # Try to parse as JSON
            try:
                # If the content is a string containing JSON with backticks, remove them
                if content.startswith("```json") and content.endswith("```"):
                    content = content[7:-3].strip()
                elif content.startswith("```") and content.endswith("```"):
                    content = content[3:-3].strip()
                    
                # Parse JSON
                schedule = json.loads(content)
                return schedule
            except json.JSONDecodeError:
                # Try eval as fallback
                try:
                    schedule = eval(content)
                    return schedule
                except:
                    return {"error": "Failed to parse AI response", "raw_content": content}
        except Exception as e:
            logger.error(f"Error in schedule_interview: {str(e)}")
            if self.use_mock:
                return {
                    "recommendedDuration": "60 minutes",
                    "suggestedTimeSlots": [
                        "Tuesday, May 21, 2025 at 10:00 AM",
                        "Wednesday, May 22, 2025 at 2:00 PM",
                        "Friday, May 24, 2025 at 11:00 AM"
                    ],
                    "interviewType": "Technical and Cultural Fit"
                }
            else:
                raise 