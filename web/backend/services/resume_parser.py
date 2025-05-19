import os
import tempfile
import re
from typing import Dict, Any
from pdfminer.high_level import extract_text
from pdfminer.pdfparser import PDFSyntaxError

class ResumeParser:
    def __init__(self):
        # No need for S3 client here as we're using StorageService for that
        pass

    async def parse_resume(self, file_content: bytes) -> str:
        """
        Parse a resume and return its content as text.
        """
        try:
            # Create a temporary file to store the PDF content
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
                temp_file.write(file_content)
                temp_file_path = temp_file.name

            try:
                # Extract text from PDF
                text = extract_text(temp_file_path)
                if not text.strip():
                    raise ValueError("PDF parsing resulted in empty text")
                return text
            finally:
                # Clean up the temporary file
                os.unlink(temp_file_path)
        except (PDFSyntaxError, ValueError) as e:
            # If PDF parsing fails, return a placeholder for now
            # TODO: Implement better error handling or fallback parsing
            return f"Error parsing PDF: {str(e)}"

    async def extract_structured_data(self, resume_content: str) -> Dict[str, Any]:
        """
        Extract structured data from resume content.
        """
        # Initialize structured data
        structured_data = {
            "name": "",
            "email": "",
            "phone": "",
            "skills": [],
            "experience": [],
            "education": []
        }

        # Split content into lines and clean them
        lines = [line.strip() for line in resume_content.split('\n') if line.strip()]

        # Extract name using multiple approaches
        name_found = False
        
        # Common name section indicators
        name_headers = ['name:', 'full name:', 'candidate:', 'applicant:']
        
        # First try to find name with explicit header
        for i, line in enumerate(lines[:10]):  # Check first 10 lines
            line_lower = line.lower()
            for header in name_headers:
                if line_lower.startswith(header):
                    # Extract name after the header
                    name = line[len(header):].strip()
                    if name:
                        structured_data["name"] = name
                        name_found = True
                        break
            if name_found:
                break

        # If no name found with header, try to identify name by pattern
        if not name_found:
            # Look for a name-like pattern in the first few lines
            name_pattern = r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+$'  # Matches "FirstName LastName" pattern
            for line in lines[:5]:  # Check first 5 lines
                if re.match(name_pattern, line):
                    structured_data["name"] = line
                    name_found = True
                    break

        # If still no name found, use first line as fallback
        if not name_found and lines:
            # Remove common resume headers if present
            first_line = lines[0]
            if first_line.lower() not in ['resume', 'curriculum vitae', 'cv']:
                structured_data["name"] = first_line

        # Extract email and phone
        email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
        phone_pattern = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
        
        for line in lines:
            # Find email
            email_match = re.search(email_pattern, line)
            if email_match:
                structured_data["email"] = email_match.group(0)
            
            # Find phone
            phone_match = re.search(phone_pattern, line)
            if phone_match:
                structured_data["phone"] = phone_match.group(0)

        # Extract education
        education_section = False
        education_entries = []
        current_edu = {}
        for i, line in enumerate(lines):
            # Start of education section
            if re.search(r'education|university|college|degree|bachelor|master|phd', line.lower()):
                education_section = True
                continue
            if education_section:
                # End of education section
                if re.search(r'experience|work|employment|skills|projects', line.lower()):
                    education_section = False
                    if current_edu:
                        education_entries.append(current_edu)
                        current_edu = {}
                    continue
                # Try to extract degree
                degree_match = re.search(r'(Bachelor|B\.S\.|BS|Master|M\.S\.|MS|PhD|Doctor|Associate|Bachelors|Masters|BA|MA|MBA|JD|MD)', line, re.IGNORECASE)
                if degree_match:
                    current_edu['degree'] = degree_match.group(0)
                # Try to extract school/university
                school_match = re.search(r'(University|College|Institute|School|Academy|Polytechnic|State University|Tech)', line, re.IGNORECASE)
                if school_match:
                    current_edu['school'] = line.strip()
                # Try to extract year
                year_match = re.search(r'(19|20)\d{2}', line)
                if year_match:
                    current_edu['year'] = year_match.group(0)
                # If we have at least degree and year, consider this a complete entry
                if 'degree' in current_edu and 'year' in current_edu:
                    education_entries.append(current_edu)
                    current_edu = {}
        # Add any remaining entry
        if current_edu:
            education_entries.append(current_edu)
        structured_data['education'] = education_entries

        # Extract experience
        experience_section = False
        current_experience = {}
        current_company = ""
        
        for line in lines:
            # Skip lines that look like contact information
            if re.search(r'(?:Mobile|Phone|Tel|Telephone)[:\s]*[\+\d\-\(\)\s]+', line):
                continue
                
            if re.search(r'experience|work|employment', line.lower()):
                experience_section = True
                continue
            
            if experience_section:
                if re.search(r'education|skills|projects', line.lower()):
                    experience_section = False
                    if current_experience:
                        structured_data["experience"].append(current_experience)
                        current_experience = {}
                    continue
                
                # Try to extract experience details
                if re.search(r'\d{4}', line):  # Year pattern
                    if current_experience:
                        structured_data["experience"].append(current_experience)
                    
                    # Look for company name in the next line
                    company_line = ""
                    for next_line in lines[lines.index(line) + 1:]:
                        if not re.search(r'\d{4}', next_line) and not re.search(r'experience|education|skills|projects', next_line.lower()):
                            company_line = next_line
                            break
                    
                    current_experience = {
                        "title": line,
                        "company": company_line.strip(),
                        "duration": re.search(r'\d{4}', line).group(0)
                    }

        # Add the last experience if exists
        if current_experience:
            structured_data["experience"].append(current_experience)

        # Extract skills
        skills_section = False
        programming_languages = []
        technical_skills = []
        
        for line in lines:
            if re.search(r'skills|technologies|tools|languages|programming', line.lower()):
                skills_section = True
                continue
            
            if skills_section:
                if re.search(r'experience|education|projects', line.lower()):
                    skills_section = False
                    continue
                
                # Add skills (comma-separated or bullet points)
                skills = [skill.strip() for skill in re.split(r'[,•]', line) if skill.strip()]
                
                # Categorize skills
                for skill in skills:
                    # Common programming languages
                    if re.search(r'\b(java|python|javascript|typescript|ruby|php|c\+\+|c#|swift|kotlin|go|rust|scala|perl|r|matlab|sql|html|css)\b', skill.lower()):
                        programming_languages.append(skill)
                    # Other technical skills
                    elif re.search(r'\b(aws|azure|gcp|docker|kubernetes|react|angular|vue|node|express|django|flask|spring|git|jenkins|agile|scrum|linux|unix|windows|macos)\b', skill.lower()):
                        technical_skills.append(skill)
                    else:
                        structured_data["skills"].append(skill)
        
        # Add categorized skills
        structured_data["programming_languages"] = programming_languages
        structured_data["technical_skills"] = technical_skills

        return structured_data 