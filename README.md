# Recruiter Infrastructure

A Kubernetes-native system for automated resume parsing and candidate scoring, powered by DigitalOcean's AI platform.

## Features

- Kubernetes Custom Resource Definition (CRD) for managing candidate profiles
- Resume parsing with PDFMiner and OpenAI fallback
- Advanced candidate analysis using DigitalOcean's AI platform
- Automated interview question generation
- Interview scheduling recommendations
- Structured data extraction from resumes
- Integration with DigitalOcean AI agents for chatbot functionality

## Prerequisites

- Python 3.8+
- Kubernetes cluster
- DigitalOcean account with AI platform access
- OpenAI API key (for fallback resume parsing)
- DigitalOcean AI agent (for chatbot functionality)

## Installation

1. Install the required Python packages:
```bash
pip install -r requirements.txt
```

2. Apply the CRD:
```bash
kubectl apply -f crd/candidateprofile.yaml
```

3. Set up environment variables:
```bash
export DIGITALOCEAN_TOKEN=your_do_token_here
export OPENAI_API_KEY=your_openai_key_here
export DO_AI_AGENT_ID=your_agent_id_here
```

## Usage

1. Create a CandidateProfile resource:
```yaml
apiVersion: recruiter.daleyarborough.com/v1
kind: CandidateProfile
metadata:
  name: example-candidate
spec:
  name: "John Doe"
  email: "john@example.com"
  resumeUrl: "https://example.com/resume.pdf"
  status: "pending"
```

2. The operator will automatically:
   - Parse the resume
   - Extract structured data
   - Analyze the candidate using DigitalOcean AI
   - Generate interview questions
   - Create interview scheduling recommendations
   - Update the resource status with all information
   - Send data to the DigitalOcean AI agent (if configured)

## Development

### Project Structure

```
.
├── crd/
│   └── candidateprofile.yaml
├── operator/
│   └── controller.py
├── services/
│   ├── resume_parser.py
│   └── ai_service.py
├── web/
│   ├── backend/
│   │   └── main.py
│   └── frontend/
├── AGENT-INTEGRATION.md
├── requirements.txt
└── README.md
```

### Running the Operator

```bash
kopf run operator/controller.py
```

## AI Features

The system leverages DigitalOcean's AI platform to provide:

1. **Candidate Analysis**
   - Overall fit scoring
   - Skills assessment
   - Experience evaluation
   - Education assessment
   - Cultural fit analysis

2. **Interview Preparation**
   - Technical questions generation
   - Behavioral questions
   - Problem-solving scenarios
   - Culture fit questions

3. **Interview Scheduling**
   - Recommended interview stages
   - Duration suggestions
   - Interviewer recommendations
   - Technical assessment planning

4. **AI Agent Integration**
   - Resume data automatically sent to DigitalOcean AI agent
   - Chatbot that can answer questions about candidates
   - For more details, see [AGENT-INTEGRATION.md](./AGENT-INTEGRATION.md)

## License

MIT # recruiter-ai
