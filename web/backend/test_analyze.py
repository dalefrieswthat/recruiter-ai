import requests
import json

def test_resume_analysis():
    # Load job requirement from JSON file
    with open('test_job_requirement.json', 'r') as f:
        job_requirement = json.dumps(json.load(f))
    
    # Read resume file as bytes
    with open('../test_resume/Dale Yarborough.pdf', 'rb') as f:
        resume_content = f.read()
    
    # Prepare files for upload
    files = {
        'file': ('resume.pdf', resume_content, 'application/pdf')
    }
    
    # Add job requirement as form data
    data = {
        'job_requirement': job_requirement
    }
    
    # Make the request
    response = requests.post(
        'http://localhost:8000/api/analyze',
        files=files,
        data=data
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")

if __name__ == "__main__":
    test_resume_analysis() 