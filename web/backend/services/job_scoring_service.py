import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class JobScoringService:
    def __init__(self):
        self.default_weights = {
            "technicalSkills": 0.4,
            "experience": 0.3,
            "education": 0.2,
            "culturalFit": 0.1
        }

    def calculate_role_specific_score(self, candidate_data: Dict[str, Any], job_requirement: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate a role-specific score for a candidate based on job requirements.
        """
        try:
            # Get scoring weights from job requirement or use defaults
            weights = job_requirement.get("spec", {}).get("scoringWeights", self.default_weights)
            
            # Calculate individual component scores
            technical_score = self._calculate_technical_score(
                candidate_data.get("analysis", {}).get("technical_skills", {}),
                job_requirement.get("spec", {}).get("requiredSkills", {})
            )
            
            experience_score = self._calculate_experience_score(
                candidate_data.get("analysis", {}).get("experience_level", "Unknown"),
                job_requirement.get("spec", {}).get("requiredExperience", {})
            )
            
            education_score = self._calculate_education_score(
                candidate_data.get("structured_data", {}).get("education", []),
                job_requirement.get("spec", {}).get("requiredEducation", {})
            )
            
            cultural_score = self._calculate_cultural_score(
                candidate_data.get("analysis", {}).get("cultural_fit", 0),
                job_requirement.get("spec", {}).get("culturalRequirements", {})
            )
            
            # Calculate weighted overall score
            overall_score = (
                technical_score * weights["technicalSkills"] +
                experience_score * weights["experience"] +
                education_score * weights["education"] +
                cultural_score * weights["culturalFit"]
            )
            
            # Prepare detailed scoring breakdown
            scoring_breakdown = {
                "overall_score": round(overall_score, 2),
                "components": {
                    "technical_skills": {
                        "score": round(technical_score, 2),
                        "weight": weights["technicalSkills"],
                        "weighted_score": round(technical_score * weights["technicalSkills"], 2)
                    },
                    "experience": {
                        "score": round(experience_score, 2),
                        "weight": weights["experience"],
                        "weighted_score": round(experience_score * weights["experience"], 2)
                    },
                    "education": {
                        "score": round(education_score, 2),
                        "weight": weights["education"],
                        "weighted_score": round(education_score * weights["education"], 2)
                    },
                    "cultural_fit": {
                        "score": round(cultural_score, 2),
                        "weight": weights["culturalFit"],
                        "weighted_score": round(cultural_score * weights["culturalFit"], 2)
                    }
                },
                "job_requirement": {
                    "title": job_requirement.get("spec", {}).get("title", "Unknown"),
                    "department": job_requirement.get("spec", {}).get("department", "Unknown")
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            return scoring_breakdown
            
        except Exception as e:
            logger.error(f"Error calculating role-specific score: {str(e)}")
            raise

    def _calculate_technical_score(self, candidate_skills: Dict[str, Any], required_skills: Dict[str, Any]) -> float:
        """
        Calculate technical skills score based on required skills.
        """
        if not required_skills:
            return 0.0
            
        total_score = 0.0
        total_required = 0
        
        # Process each skill category
        for category in ["programmingLanguages", "frameworks", "cloudAndDevOps", "tools"]:
            required = required_skills.get(category, {})
            candidate = candidate_skills.get(category, {})
            
            for skill, min_level in required.items():
                total_required += 1
                candidate_level = candidate.get(skill, 0)
                
                # Calculate score based on how well the candidate meets the requirement
                if candidate_level >= min_level:
                    total_score += 1.0
                else:
                    # Partial credit for being close to the requirement
                    total_score += max(0, candidate_level / min_level)
        
        return (total_score / total_required) * 100 if total_required > 0 else 0.0

    def _calculate_experience_score(self, candidate_level: str, required_experience: Dict[str, Any]) -> float:
        """
        Calculate experience score based on required experience level and years.
        """
        if not required_experience:
            return 0.0
            
        required_level = required_experience.get("level", "Mid-level")
        required_years = required_experience.get("years", 0)
        
        # Map experience levels to numeric values
        level_values = {
            "Junior": 1,
            "Mid-level": 2,
            "Senior": 3,
            "Lead": 4
        }
        
        candidate_value = level_values.get(candidate_level, 0)
        required_value = level_values.get(required_level, 0)
        
        # Calculate score based on level match
        if candidate_value >= required_value:
            return 100.0
        else:
            # Partial credit based on how close they are to the requirement
            return (candidate_value / required_value) * 100

    def _normalize_degree(self, degree: str) -> str:
        """
        Normalize degree names to standard categories.
        """
        degree = degree.lower()
        if any(x in degree for x in ["bachelor", "b.s.", "bs", "ba"]):
            return "Bachelor"
        if any(x in degree for x in ["master", "m.s.", "ms", "ma", "mba"]):
            return "Master"
        if any(x in degree for x in ["phd", "doctor", "ph.d.", "md", "jd"]):
            return "PhD"
        if "associate" in degree:
            return "Associate"
        if "high school" in degree:
            return "High School"
        return degree.title()

    def _calculate_education_score(self, candidate_education: List[Dict[str, Any]], required_education: Dict[str, Any]) -> float:
        """
        Calculate education score based on required education level and preferred fields.
        """
        if not required_education or not candidate_education:
            return 0.0
        required_degree = required_education.get("minimumDegree", "Bachelor")
        preferred_fields = required_education.get("preferredFields", [])
        # Map degrees to numeric values
        degree_values = {
            "High School": 1,
            "Associate": 2,
            "Bachelor": 3,
            "Master": 4,
            "PhD": 5
        }
        # Find highest degree (normalized)
        highest_degree = "High School"
        for edu in candidate_education:
            degree = self._normalize_degree(edu.get("degree", ""))
            if degree in degree_values and degree_values[degree] > degree_values.get(highest_degree, 0):
                highest_degree = degree
        # Calculate base score from degree level
        candidate_value = degree_values.get(highest_degree, 0)
        required_value = degree_values.get(required_degree, 0)
        if candidate_value >= required_value:
            base_score = 100.0
        else:
            base_score = (candidate_value / required_value) * 100 if required_value else 0
        # Check for preferred fields (case-insensitive, partial match)
        field_bonus = 0
        if preferred_fields:
            for edu in candidate_education:
                field = edu.get("degree", "").lower()
                if any(pref.lower() in field for pref in preferred_fields):
                    field_bonus = 20
                    break
        return min(100, base_score + field_bonus)

    def _calculate_cultural_score(self, candidate_cultural_fit: float, cultural_requirements: Dict[str, Any]) -> float:
        """
        Calculate cultural fit score based on required cultural attributes.
        """
        if not cultural_requirements:
            return candidate_cultural_fit
            
        total_score = 0.0
        total_required = 0
        
        for attribute, required_level in cultural_requirements.items():
            total_required += 1
            # For now, we'll use the overall cultural fit score
            # In a real implementation, we would have specific scores for each attribute
            if candidate_cultural_fit >= required_level:
                total_score += 1.0
            else:
                total_score += max(0, candidate_cultural_fit / required_level)
        
        return (total_score / total_required) * 100 if total_required > 0 else candidate_cultural_fit 